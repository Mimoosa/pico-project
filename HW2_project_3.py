from machine import ADC, Pin, I2C # For controlling pins and I2C interface
from piotimer import Piotimer  # Timer for periodic operations
from ssd1306 import SSD1306_I2C  # Import the SSD1306 OLED display driver
from fifo import Fifo # FIFO queue for buffering data
import time # Import time module for timing operations
import micropython # MicroPython utilities
micropython.alloc_emergency_exception_buf(200) # Allocate buffer for emergency exception handling
import network
from time import sleep
from umqtt.simple import MQTTClient
import ujson
import urequests as requests 


# Define a class to manage the heart rate monitoring device
class Pico:
    def __init__(self, sw1_pin, sensor_pin, rot_a, rot_b, e_switch):
        # Initialize the rotary encoder pins
        self.a = Pin(rot_a, mode=Pin.IN, pull=Pin.PULL_UP) # Pin for encoder A
        self.b = Pin(rot_b, mode=Pin.IN, pull=Pin.PULL_UP) # Pin for encoder B
        self.encoder_switch = Pin(e_switch, mode=Pin.IN, pull=Pin.PULL_UP) # Pin for the encoder switch
        
        # Initialize switch pins with pull-up resistors
        self.switch1 = Pin(sw1_pin, mode = Pin.IN, pull = Pin.PULL_UP)
        # Initialize the ADC for the heart rate sensor
        self.sensor = ADC(Pin(sensor_pin))
        
        # Set up I2C communication for OLED display
        self.i2c = I2C(1, scl=Pin(15), sda=Pin(14), freq=400000) # Initialize I2C for OLED
        self.oled_width = 128 # OLED width
        self.oled_height = 64 # OLED height
        self.oled = SSD1306_I2C(self.oled_width, self.oled_height, self.i2c) # Create OLED object
        
        # Initialize FIFO queues for button, sensor, and encoder events
        self.button_fifo = Fifo(30, typecode='i') # FIFO for button events
        self.sensor_fifo = Fifo(500, typecode='i') # FIFO for sensor readings
        self.encoder_fifo = Fifo(30, typecode='i') # FIFO for encoder events
        
        # Variables to manage debounce for buttons
        self.last_press_time_sw1 = 0 # Last press time for SW_1
        self.last_press_time_encoder_switch = 0 # Last press time for encoder switch 

        # Set up an interrupt for SW_1 button press
        self.switch1.irq(handler=self.button_handler_sw1, trigger=Pin.IRQ_RISING, hard=True) # Set up interrupt for button press
        
        # Set up a timer to read sensor data periodically
        self.sensor_timer = None
        
        # Set up interrupts for rotary encoder turns and clicks
        self.a.irq(handler=self.turning_encoder_handler, trigger=Pin.IRQ_RISING, hard=True) # Encoder turn event
        self.encoder_switch.irq(handler=self.button_handler_encoder, trigger=Pin.IRQ_RISING, hard=True) # Encoder button press
        
        # Initialize various states and measurement variables
        self.option = 0 # Initialize highlighted menu item
        self.measurement_on = False# Flag to indicate if measurement is active
        self.screen_timer = None # Timer for screen updates  
        self.threshold = 0 # Peak detection threshold
        self.thresval = 0.9 # Relative threshold multiplier
        self.max_value = 0 # Maximum sensor value for peak detection
        self.count = 0 # Counter for samples
        self.peaks = [] # List of detected peak positions
        self.hr_display_flag = False # Flag for updating the OLED screen
        self.hr_values = [] # List of calculated heart rate values
        self.hr_value = 0 # Current heart rate value to display
        self.ppi_intervals = []  # List of Peak-to-Peak Intervals (PPI)
        self.SSID = "KME751_Group_8"
        self.PASSWORD = "MMN8MMN8"
        self.BROKER_IP = "192.168.8.253"
        self.wlan = None
        #self.connect_wlan()
        self.mqtt_client = None
        #self.connect_mqtt()
        self.json_message = None
        self.APIKEY = "pbZRUi49X48I56oL1Lq8y8NDjq6rPfzX3AQeNo3a"  
        self.CLIENT_ID = "3pjgjdmamlj759te85icf0lucv"  
        self.CLIENT_SECRET = "111fqsli1eo7mejcrlffbklvftcnfl4keoadrdv1o45vt9pndlef"   
        self.LOGIN_URL = "https://kubioscloud.auth.eu-west-1.amazoncognito.com/login"  
        self.TOKEN_URL = "https://kubioscloud.auth.eu-west-1.amazoncognito.com/oauth2/token"  
        self.REDIRECT_URI = "https://analysis.kubioscloud.com/v1/portal/login"
        self.kubios_response = {}
        self.pns_heart = None
        self.sns_heart = None
        
        


    def turning_encoder_handler(self, pin):
        # Handler for rotary encoder turn events
        if self.b(): # Check the state of encoder B
            self.encoder_fifo.put(-1) # Put a value to indicate counter-clockwise turn
            
        else:
            self.encoder_fifo.put(1) # Put a value to indicate clockwise turn
            
    def button_handler_encoder(self, pin):
        # Handler for encoder button presses
        current_time = time.ticks_ms() # Get the current time in milliseconds
      
        if current_time - self.last_press_time_encoder_switch > 50:  # Check if the press interval is greater than 50 ms
            self.encoder_fifo.put(2) # Put a value to indicate button press
            self.last_press_time_encoder_switch = current_time # Update last press time
            
    # Interrupt handler for SW_1 button press
    def button_handler_sw1(self, pin):
         # Handler for SW1 button presses
        current_time = time.ticks_ms() # Get the current time in milliseconds

        if current_time - self.last_press_time_sw1 > 50:  # Check if the press interval is greater than 50 ms
            self.button_fifo.put(2) # Put a value to indicate SW_1 press
            self.last_press_time_sw1 = current_time # Update last press time
            
    def display_menu(self):
        # Display the menu on the OLED screen
        self.oled.fill(0) # Clear the OLED screen
        
        y_position = 0
        
        options = ["MEASURE HR", "BASIC HRV ANALYSIS", "KUBIOS", "HISTORY"]
     
        
        for i in range(4):
            if i == self.option: # Highlight the selected option
                self.oled.fill_rect(0, y_position, self.oled_width, 8, 1) # Draw highlight rectangle
                self.oled.text(options[i], 0, y_position, 0) # Display highlighted option in black color

            else:
                self.oled.text(options[i], 0, y_position, 1) # Display other options in white color

            y_position += 12 # Move down for the next option

        self.oled.show() # Update the OLED display with new content
        
         
    def display_instruction1(self):
        # Display instructions for starting heart rate measurement
        self.oled.fill(0)  # Clear the OLED screen
        line1 = "START" # Instruction text
        line2 = "MEASUREMENT BY"
        line3 = "PRESSING YOUR"
        line4 = "FINGER ON THE"
        line5 = "SENSOR AND PRESS"
        line6 = "THE SW1 BUTTON"
        # Display each line of instruction text on the OLED
        self.oled.text(line1, 0, int(self.oled_height / 2) - 30, 1) 
        self.oled.text(line2, 0, int(self.oled_height / 2) - 20, 1)
        self.oled.text(line3, 0, int(self.oled_height / 2) - 10, 1)
        self.oled.text(line4, 0, int(self.oled_height / 2), 1)
        self.oled.text(line5, 0, int(self.oled_height / 2) + 10, 1)
        self.oled.text(line6, 0, int(self.oled_height / 2) + 20, 1)
        
        self.oled.show() # Update the OLED display
        
    def display_instruction_HR(self):
        # Display instructions for stopping heart rate measurement
        self.oled.fill(0) # Clear OLED screen
        instruction_line1 = "PRESS THE BUTTON"
        instruction_line2 = "TO STOP"
        self.oled.text(instruction_line1, 0, int(self.oled_height / 2) + 10, 1)
        self.oled.text(instruction_line2, 0, int(self.oled_height / 2) + 20, 1)
        self.oled.show() # Update the OLED display
        
    # Clear the sensor FIFO by consuming all data        
    def empty_sensor_fifo(self):
        while self.sensor_fifo.has_data():
            self.sensor_fifo.get()
        
    
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
                        if self.option == 1 or self.option == 2: # If the HRV analysis or the Kubios menu is selected
                            self.ppi_intervals.append(int(ppi_seconds*1000)) # Store the PPI value in milliseconds
                        
    
    def set_sensor_timer(self):
        # Set up a timer to read sensor data periodically
        self.sensor_timer = Piotimer(period=4, mode=Piotimer.PERIODIC, callback=self.read_sensor)                      
    
    
    def set_screen_timer(self):
        # Set a timer to periodically update the OLED display
        self.screen_timer = Piotimer(period=5000, mode=Piotimer.PERIODIC, callback=pico.display_hr_flag)


    def display_hr_flag(self, timer):
        # Set a flag to indicate that the OLED screen should be updated
        if self.hr_values:  # Check if there are any calculated heart rate values in the hr_values list.
            self.hr_display_flag = True  # Set the flag to True to indicate the display needs to be updated.
            
    
    # Update the OLED with the current heart rate
    def display_hr(self):
        self.oled.fill_rect(0, int(self.oled_height / 2) - 10, self.oled_width, 20, 0) # Clear previous text 
    
        hr_value_line = f"{self.hr_value} BPM" # Display heart rate
       
        self.oled.text(hr_value_line, 0, int(self.oled_height / 2) - 10, 1) # Display heart rate
        
        self.oled.show() # Update the OLED display


    def calculate_rmssd(self):
        # Calculate RMSSD (Root Mean Square of Successive Differences)
        differences = [] # List to store successive differences
        for i in range(len(self.ppi_values) - 1): 
            difference = self.ppi_values[i + 1] - self.ppi_values[i] # Calculate the difference between consecutive PPI values
            differences.append(difference) # Store the difference
        
        squared_differences = [] # Square the differences
        for diff in differences:
            squared_differences.append(diff**2)
            
        mean_squared_difference = sum(squared_differences) / len(squared_differences) # Calculate the mean squared difference
        
        
    
        return int(mean_squared_difference ** 0.5)  # Calculate the square root of the mean squared difference and return it
    
    
    def calculate_sdnn(self, m_ppi):
        # Calculate SDNN (Standard Deviation of NN intervals)
        
        # Calculate squared differences from the mean PPI
        differences = []
        for i in range(len(self.ppi_values)):
            difference = m_ppi - self.ppi_values[i]
            differences.append(difference ** 2)
        # Calculate the average of the squared differences
        avg_differences = sum(differences) / len(differences)
        
        return int(avg_differences ** 0.5) # Calculate the square root of the average squared difference and return int
        

    def calculate_hrv(self):
        # Calculate HRV metrics (mean HR, mean PPI, RMSSD, and SDNN)
        mean_hr = int(sum(self.hr_values) / len(self.hr_values))  # Calculate the mean heart rate
        mean_ppi = int(sum(self.ppi_intervals) / len(self.ppi_intervals)) # Calculate the mean PPI
        rmssd = self.calculate_rmssd()
        sdnn = self.calculate_sdnn(mean_ppi)
        measurement = { 
                        "mean_hr": mean_hr, 
                        "mean_ppi": mean_ppi, 
                        "rmssd": rmssd, 
                        "sdnn": sdnn 
                        } 
        self.json_message = ujson.dumps(measurement)
        
        print(f"MEAN HR: {mean_hr}")
        print(f"MEAN PPI: {mean_ppi}")
        print(f"RMSSD: {rmssd}")
        print(f"SDNN: {sdnn}")
        
        if pico.option == 1:
            self.send_mqtt_message()
        
    
    def send_mqtt_message(self):
        
        if self.json_message: 
            topic = "project"
            message = self.json_message
            self.mqtt_client.publish(topic, message)
            print(f"Sending to MQTT: {topic} -> {message}")


    def connect_wlan(self):
        # Connecting to the group WLAN
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        self.wlan.connect(self.SSID, self.PASSWORD)
        
        while self.wlan.isconnected() == False:
            print("Connecting... ")
            sleep(1)



        print("Connection successful. Pico IP:", self.wlan.ifconfig()[0]) 


    def connect_mqtt(self):
        self.mqtt_client=MQTTClient("", self.BROKER_IP)
        self.mqtt_client.connect(clean_session=True)
        

    def get_response_data_from_Kubios(self):
        response = requests.post(  
            url = self.TOKEN_URL,   
            data = 'grant_type=client_credentials&client_id={}'.format(self.CLIENT_ID),  
            headers = {'Content-Type':'application/x-www-form-urlencoded'},  
            auth = (self.CLIENT_ID, self.CLIENT_SECRET))
        
             
        response = response.json() #Parse JSON response into a python dictionary  
        access_token = response["access_token"] #Parse access token 
                
        dataset = { 
            "type": "RRI", 
            "data": self.ppi_intervals, 
            "analysis": {"type": "readiness"} 
            } 
        # Make the readiness analysis with the given data 
        response = requests.post( 
            url = "https://analysis.kubioscloud.com/v2/analytics/analyze", 
            headers = { "Authorization": "Bearer {}".format(access_token), #use access token to access your Kubios Cloud analysis session 
                        "X-Api-Key": self.APIKEY}, 
            json = dataset) #dataset will be automatically converted to JSON by the urequests library  
         
        response = response.json() 
         
        mean_hr = int(response["analysis"]["mean_hr_bpm"])  
        mean_ppi = int(response["analysis"]["mean_rr_ms"])  
        rmssd = int(response["analysis"]["rmssd_ms"])      # RMSSD
        sdnn = int(response["analysis"]["sdnn_ms"])        # SDNN
        pns = response["analysis"]["pns_index"]
        sns = response["analysis"]["sns_index"]
        
        self.kubios_response = {"k_mean_hr": mean_hr, "k_mean_ppi": mean_ppi, "k_rmssd": rmssd, "k_sdnn": sdnn, "k_pns": f"{pns:.3f}", "k_sns": f"{sns:.3f}",}
        if pns < -1 :
            self.pns_heart = "+"
        elif pns > -1 and pns < 1:
            self.pns_heart = "++"
        elif pns > 1:
            self.pns_heart = "+++"
            
        if sns < -1 :
            self.sns_heart = "+++"
        elif sns > -1 and sns < 1:
            self.sns_heart = "++"
        elif sns > 1:
            self.sns_heart = "+"
            
            
        if self.kubios_response:
            self.display_kubios_response()
        
        
    def display_kubios_response(self):
        # Display instructions for stopping heart rate measurement
        y_position = 0
        self.oled.fill(0) # Clear OLED screen
        hr_line = f"MEAN HR: {self.kubios_response["k_mean_hr"]}"
        ppi_line = f"MEAN PPI: {self.kubios_response["k_mean_ppi"]}"
        rmssd_line = f"RMSSD: {self.kubios_response["k_rmssd"]}"
        sdnn_line = f"SDNN: {self.kubios_response["k_sdnn"]}"
        sns_line = f"SNS: {self.kubios_response["k_sns"]} {self.sns_heart}"
        pns_line = f"PNS: {self.kubios_response["k_pns"]} {self.pns_heart}"
        
        response_list = [hr_line, ppi_line, rmssd_line, sdnn_line, sns_line, pns_line]
        
        for i in response_list:
            self.oled.text(i, 0, y_position, 1)
            
            y_position += 10
            
        self.oled.show() # Update the OLED display



# Instantiate the Pico class with appropriate GPIO pin numbers
# sw1_pin=8, sensor_pin=27, rot_a=10, rot_b=11, e_switch=12
pico = Pico(8, 27, 10, 11, 12)

# Display the main menu on the OLED screen
pico.display_menu()

# Main loop to process events and update heart rate
while True:
    if not pico.measurement_on:
        pico.empty_sensor_fifo() # Clear FIFO if measurement is off

    # Handle events from the rotary encoder (turns and button press)
    if pico.encoder_fifo.has_data():
        encoder_data = pico.encoder_fifo.get() # Get the data from the FIFO
        
        if encoder_data == 2: # If the encoder button is pressed
            pico.display_instruction1()  # Show the instructions for starting measurement
     
        
        if encoder_data == -1: # Check for counter-clockwise turn event
            if pico.option > 0: # Ensure it doesn't go out of bounds
                pico.option -= 1 # Move highlight up in the menu
                pico.display_menu() # Update the menu display
                
        elif encoder_data == 1:  # Check for clockwise turn event
            if pico.option < 3:  # Ensure it doesn't exceed the menu options
                pico.option += 1 # Move highlight down in the menu
                pico.display_menu() # Update the menu display
    
    # Handle events from the SW1 button
    if pico.button_fifo.has_data():
        button_data = pico.button_fifo.get() # Get the data from the FIFO queue

        if button_data == 2: # If SW_1 button press is detected
            if pico.measurement_on: # If measurement is currently active
                pico.measurement_on = False # Stop measurement
                pico.count = 0 # Reset the sample counter
                pico.display_menu() # Return to the main menu
                pico.peaks = [] # Clear the list of detected peaks
                pico.hr_values = []  # Clear the heart rate values
                pico.empty_sensor_fifo() # Clear FIFO
                if pico.sensor_timer:  # Check if screen_timer exists
                    pico.sensor_timer.deinit()  # Stop the screen_timer
                    pico.sensor_timer = None  # Reset screen_timer reference
                
                if pico.option == 0: # If in heart rate measurement mode
                    if pico.screen_timer:  # Check if screen_timer exists
                        pico.screen_timer.deinit()  # Stop the screen_timer
                        pico.screen_timer = None  # Reset screen_timer reference
                        
                elif pico.option == 1 or pico.option == 2: # If in HRV analysis or Kubios mode
                    pico.ppi_values = [] # Clear the PPI values
                    
                elif pico.option == 2:
                    pico.kubios_response = {}
                    
                    
            else: # If measurement is not currently active
                pico.set_sensor_timer()
                pico.measurement_on = True # Start measurement
                
    
    # Handle sensor data processing    
    if pico.sensor_fifo.has_data(): # Check if there is data in the FIFO
        sample = pico.sensor_fifo.get() # Get the data from the FIFO
        
        if pico.measurement_on == True:
            
            pico.count += 1 # Increment the sample counter
            
            if pico.option == 0: # If in heart rate measurement mode
                if pico.count == 1: # On the first sample
                    pico.display_instruction_HR() # Show stop instructions
                    if not pico.screen_timer:  # Avoid creating multiple timers
                        pico.set_screen_timer() # Set a screen update timer
                        
            
            if pico.count < 1000:
                pico.empty_sensor_fifo() # Ignore initial noise

            if pico.count >= 1250:
                if pico.count == 1250 or pico.count % 125 == 0:
                    pico.set_threshold()# Set threshold for peak detection
                     

                pico.detect_peaks(sample)# Detect peaks
                    
                if pico.count % 500 == 0: # Every 500 samples
                    pico.calculate_hr() # Calculate heart rate

                if pico.option == 0: # If in heart rate measurement mode
                    if pico.hr_display_flag: # Check if the OLED needs updating
                        pico.hr_value = int(pico.hr_values[-1]) # Get the latest heart rate
                        pico.display_hr() # Update OLED display with the heart rate
                        pico.hr_display_flag = False # Reset display flag
                    
                elif pico.option == 1: # If in HRV analysis mode
                    if pico.count > 8750:
                        pico.calculate_hrv() # Calculate HRV metrics (Mean HR, Mean PPI, RMSSD, SDNN)
                        
                elif pico.option == 2:
                    if pico.count > 8750 and len(pico.ppi_intervals) > 15 and not pico.kubios_response:
                         pico.get_response_data_from_Kubios() 
               
