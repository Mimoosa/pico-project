from machine import ADC, Pin, I2C # For controlling pins and I2C interface
from piotimer import Piotimer
from ssd1306 import SSD1306_I2C  # Import the SSD1306 OLED display driver
from fifo import Fifo
import time # Import time module for timing operations
import micropython
micropython.alloc_emergency_exception_buf(200) # Allocate buffer for emergency exception handling

# Define a class to manage the rotary encoder and OLED display
class Pico:
    def __init__(self, sw1_pin, sensor_pin):
        
        
        # Initialize switch pins with pull-up resistors
        self.switch1 = Pin(sw1_pin, mode = Pin.IN, pull = Pin.PULL_UP)
        self.sensor = ADC(Pin(sensor_pin))
        
        # Set up I2C communication for OLED display
        self.i2c = I2C(1, scl=Pin(15), sda=Pin(14), freq=400000) # Initialize I2C for OLED
        self.oled_width = 128 # OLED width
        self.oled_height = 64 # OLED height
        self.oled = SSD1306_I2C(self.oled_width, self.oled_height, self.i2c) # Create OLED object
        
        # Initialize Filefifo to read data from a file
        self.button_fifo = Fifo(30, typecode='i') # Create FIFO queue for events
        self.sensor_fifo = Fifo(1000, typecode='i') # Create FIFO queue for data events
        
        # Variables to manage debounce for buttons
        self.last_press_time_sw1 = 0 # Last press time for SW_1

         # Set up an interrupt for SW_1 button press
        self.switch1.irq(handler=self.button_handler, trigger=Pin.IRQ_RISING, hard=True) # Set up interrupt for button press
        self.timer = Piotimer(period=4, mode=Piotimer.PERIODIC, callback=self.read_sensor)
        self.measurement_on = False
       
        self.threshold_90 = 0
        self.thresval = 0.9
        self.prev_sample = 0
        self.max_value = self.threshold_90
        self.first_check = 0
     
        self.peaks = []
        self.hr_values = []
        

    # Interrupt handler for SW_1 button press
    def button_handler(self, pin):
        # Debounce the button to avoid false triggers
        current_time = time.ticks_ms() # Get the current time in milliseconds

        if current_time - self.last_press_time_sw1 > 50:  # Check if the press interval is greater than 50 ms
            self.button_fifo.put(2) # Put a value to indicate SW_1 press
            
            self.last_press_time_sw1 = current_time # Update last press time 
            
    def read_sensor(self, timer):    
        value = self.sensor.read_u16()
        self.sensor_fifo.put(value)
   
    # Find minimum and maximum values in the filtered data
    def set_threshold(self):
        h = max(self.sensor_fifo.data) - min(self.sensor_fifo.data)
        self.threshold_90 = min(self.sensor_fifo.data) + self.thresval * h
       
        #self.threshold = int((min(self.sensor_fifo.data) + max(self.sensor_fifo.data)) / 2)
        
    
    def detect_peaks(self, value):
        
        if value > self.max_value and value > self.threshold_90:
            
            self.max_value = value
        if value < self.max_value and value > self.threshold_90:
            self.first_check = value
            
        if value < self.max_value and value > self.threshold_90 and self.first_check > 0:
            print(self.first_check)
            print(value)
            if self.first_check > value:
                
                print(f"peak_found: {self.max_value}")
            self.first_check = 0
            self.max_value = self.threshold_90
        

    def calculate_hr(self):
        for i in range(len(self.peaks) - 1): # Loop through the detected peaks
            num_samples = self.peaks[i + 1][0] - self.peaks[i][0] # Calculate the number of samples between two consecutive peaks

            if num_samples > 0: # Ensure the sample distance is positive
                ppi_seconds = num_samples * 0.004 # Calculate the time between peaks in seconds (0.004 seconds per sample)

                if ppi_seconds > 0: # If the time between peaks is positive
                    hr = 60 / ppi_seconds # Calculate the heart rate in beats per minute (bpm)
                   
                    self.hr_values.append(hr) # Append the valid heart rate to the hr_values list
                    print(hr) # Print the heart rate value
   
   
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
    
    
    # Displays a window of 128 values on the OLED screen
    def display_window(self):
        
        self.oled.fill(0) # Clear OLED screen
        x_position = 0 # Start plotting from the leftmost pixel     
        for i in range(self.window_size):
            current_index = i + self.window_start_index # Calculate the index of the current data point
            
            y_position = int(self.scaled_data_list[current_index] * (self.oled_height - 1) / 100) # Scale to OLED height
            self.oled.pixel(x_position, y_position, 1)  # Plot the pixel on the screen
            x_position += 1  # Move to the next horizontal position
               
        self.oled.show() # Update OLED display


            
# Instantiate the Pico class with appropriate GPIO pin numbers
pico = Pico(8, 27)
pico.display_instruction() # Show initial instruction on the OLED screen

# Main loop to handle events from the FIFO queue
while True:
    if pico.button_fifo.has_data():
        button_data = pico.button_fifo.get()
        
        if button_data == 2: # If SW_1 button press is detected
            if pico.measurement_on:
                pico.measurement_on = False
            else:
                pico.measurement_on = True

        
    if pico.sensor_fifo.has_data(): # Check if there is data in the FIFO
        sample = pico.sensor_fifo.get() # Get the data from the FIFO
    
        if pico.measurement_on == True:
            pico.set_threshold()
            #pico.detect_peaks()
            #print(sample)
            #if sample > pico.threshold_90:
                #print(f"over th")
            #else:
                #print("under th")
            pico.detect_peaks(sample)