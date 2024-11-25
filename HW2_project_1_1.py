from machine import ADC, Pin, I2C # For controlling pins and I2C interface
from piotimer import Piotimer  # Timer for periodic operations
from ssd1306 import SSD1306_I2C  # Import the SSD1306 OLED display driver
from fifo import Fifo # FIFO queue for buffering data
import time # Import time module for timing operations
import micropython # MicroPython utilities
micropython.alloc_emergency_exception_buf(200) # Allocate buffer for emergency exception handling

# Define a class to manage the heart rate monitoring device
class Pico:
    def __init__(self, sw1_pin, sensor_pin):
        
        
        # Initialize switch pins with pull-up resistors
        self.switch1 = Pin(sw1_pin, mode = Pin.IN, pull = Pin.PULL_UP)
        # Initialize the ADC for the heart rate sensor
        self.sensor = ADC(Pin(sensor_pin))
        
        # Set up I2C communication for OLED display
        self.i2c = I2C(1, scl=Pin(15), sda=Pin(14), freq=400000) # Initialize I2C for OLED
        self.oled_width = 128 # OLED width
        self.oled_height = 64 # OLED height
        self.oled = SSD1306_I2C(self.oled_width, self.oled_height, self.i2c) # Create OLED object
        
         # Set up an interrupt for button presses
        self.button_fifo = Fifo(30, typecode='i') # FIFO for button events
        self.sensor_fifo = Fifo(1000, typecode='i') # FIFO for sensor readings
        
        # Variables to manage debounce for buttons
        self.last_press_time_sw1 = 0 # Last press time for SW_1

        # Set up an interrupt for SW_1 button press
        self.switch1.irq(handler=self.button_handler, trigger=Pin.IRQ_RISING, hard=True) # Set up interrupt for button press
        
         # Set up a timer to read sensor data periodically
        self.sensor_timer = Piotimer(period=4, mode=Piotimer.PERIODIC, callback=self.read_sensor)
        
        # Initialize measurement-related variables
        self.measurement_on = False# Flag to indicate if measurement is active
        self.threshold = 0 # Peak detection threshold
        self.thresval = 0.9 # Relative threshold multiplier
        self.max_value = 0 # Maximum sensor value for peak detection
        self.count = 0 # Counter for samples
        self.peaks = [] # List of detected peak positions
        self.hr_display_flag = False # Flag for updating the OLED screen
        self.hr_values = [] # List of calculated heart rate values
        self.hr_value = 0 # Current heart rate value to display
   
        

    # Interrupt handler for SW_1 button press
    def button_handler(self, pin):
        # Debounce the button to avoid false triggers
        current_time = time.ticks_ms() # Get the current time in milliseconds

        if current_time - self.last_press_time_sw1 > 50:  # Check if the press interval is greater than 50 ms
            self.button_fifo.put(2) # Put a value to indicate SW_1 press
            
            self.last_press_time_sw1 = current_time # Update last press time 
    
    # Timer callback to read sensor data and store it in the FIFO
    def read_sensor(self, timer):    
        value = self.sensor.read_u16() # Read 16-bit ADC value
        self.sensor_fifo.put(value) # Add value to the FIFO
   
    # Calculate the threshold for peak detection
    def set_threshold(self):
        h = max(self.sensor_fifo.data) - min(self.sensor_fifo.data) # Calculate range
        self.threshold = min(self.sensor_fifo.data) + self.thresval * h # Set threshold
        self.max_value = self.threshold # Initialize max_value
        
        
    # Detect peaks in the filtered signal   
    def detect_peaks(self, value):
        
        if value > self.max_value:
            self.max_value = value # Update maximum value
        elif value < self.threshold and self.max_value > self.threshold: # Check for peaks
            self.peaks.append(self.count) # Record peak position
            self.max_value = self.threshold # Reset max value
    
    # Clear the sensor FIFO by consuming all data        
    def empty_sensor_fifo(self):
        while self.sensor_fifo.has_data():
            self.sensor_fifo.get()
     
    # Calculate heart rate from detected peaks
    def calculate_hr(self):
        if len(self.peaks) > 2:
            num_samples = self.peaks[-1] - self.peaks[-2] # Time difference between peaks

            if num_samples > 0: # Ensure the sample distance is positive
                ppi_seconds = num_samples * 0.004 # Calculate the time between peaks in seconds (0.004 seconds per sample)

                if ppi_seconds > 0: # If the time between peaks is positive
                    hr = 60 / ppi_seconds # Calculate the heart rate in beats per minute (bpm)
                   
                    if hr > 30 and hr < 200: # Only consider valid heart rates
                        self.hr_values.append(hr) # Append the valid heart rate to the hr_values list
                        print(hr) # Print the heart rate value
                        self.peaks = self.peaks[-1:] # Keep only the latest peak

   
    # Display the initial instruction on the OLED screen
    def display_instruction(self):
        self.oled.fill(0)  # Clear the OLED screen
        line1 = "START" # Instruction text
        line2 = "MEASUREMENT BY"
        line3 = "PRESSING THE"
        line4 = "SW1 BUTTON"
        self.oled.text(line1, 0, int(self.oled_height / 2) - 20, 1) # Display text centered vertically
        self.oled.text(line2, 0, int(self.oled_height / 2) - 10, 1)
        self.oled.text(line3, 0, int(self.oled_height / 2), 1)
        self.oled.text(line4, 0, int(self.oled_height / 2) + 10, 1)    
        self.oled.show() # Update the OLED display
     
    # Display instructions to stop measurement
    def display_instruction2(self):
        self.oled.fill(0) # Clear OLED screen
        instruction_line1 = "PRESS THE BUTTON"
        instruction_line2 = "TO STOP"
        self.oled.text(instruction_line1, 0, int(self.oled_height / 2) + 10, 1)
        self.oled.text(instruction_line2, 0, int(self.oled_height / 2) + 20, 1)
        self.oled.show() # Update the OLED display
    
    
    
    def display_hr_flag(self, timer):
        if self.hr_values:  # Check if there are any calculated heart rate values in the hr_values list.
            self.hr_display_flag = True  # Set the flag to True to indicate the display needs to be updated.
            
        
    # Update the OLED with the current heart rate
    def display_hr(self):
        self.oled.fill_rect(0, int(self.oled_height / 2) - 10, self.oled_width, 20, 0) # Clear previous text 
    
        hr_value_line = f"{self.hr_value} BPM" # Display heart rate
       
        self.oled.text(hr_value_line, 0, int(self.oled_height / 2) - 10, 1) # Display heart rate
        
        self.oled.show() # Update the OLED display

        

            
# Instantiate the Pico class with appropriate GPIO pin numbers
pico = Pico(8, 27)
pico.display_instruction() # Show the initial instruction screen
# Set a timer to update the OLED display every 5 seconds
screen_timer = Piotimer(period=5000, mode=Piotimer.PERIODIC, callback=pico.display_hr_flag)

# Main loop to process events and update heart rate
while True:
    if not pico.measurement_on:
        pico.empty_sensor_fifo() # Clear FIFO if measurement is off
        
    # Handle button press events
    if pico.button_fifo.has_data():
        button_data = pico.button_fifo.get()
        
        if button_data == 2: # If SW_1 button press is detected
            if pico.measurement_on:
                pico.measurement_on = False # Stop measurement
                pico.count = 0 # Reset counter
                pico.display_instruction() # Show initial instruction
                pico.empty_sensor_fifo() # Clear FIFO
                
            else:
                pico.measurement_on = True # Start measurement
                

    # Handle sensor data processing    
    if pico.sensor_fifo.has_data(): # Check if there is data in the FIFO
        sample = pico.sensor_fifo.get() # Get the data from the FIFO
        
        if pico.measurement_on == True:
            
            pico.count += 1
            if pico.count == 1:
                pico.display_instruction2() # Show stop instruction
            if pico.count < 750:
                pico.empty_sensor_fifo() # Ignore initial noise
            
            if pico.count >= 1000:
                if pico.count == 1000:
                    pico.set_threshold()# Set threshold for peak detection
                    print(pico.threshold)
             
                pico.detect_peaks(sample)# Detect peaks
                
                if pico.count % 500 == 0:
                    pico.calculate_hr() # Calculate heart rate
                
                if pico.hr_display_flag:
                    pico.hr_value = int(pico.hr_values[-1]) # Get the latest heart rate
                    pico.display_hr() # Update OLED
                    pico.hr_display_flag = False # Reset display flag
            
