from machine import ADC, Pin, I2C # For controlling pins and I2C interface
from piotimer import Piotimer  # Timer for periodic operations
from ssd1306 import SSD1306_I2C  # Import the SSD1306 OLED display driver
from fifo import Fifo # FIFO queue for buffering data
import time # Import time module for timing operations
import micropython # MicroPython utilities
micropython.alloc_emergency_exception_buf(200) # Allocate buffer for emergency exception handling
import network# For WiFi connectivity
from time import sleep # For delays
from umqtt.simple import MQTTClient # For MQTT messaging
import ujson # For JSON handling



# Define a class to manage the heart rate monitoring device
class Pico:
    def __init__(self, sw2_pin, sw1_pin, sensor_pin, rot_a, rot_b, e_switch):
        # Initialize the rotary encoder pins
        self.a = Pin(rot_a, mode=Pin.IN, pull=Pin.PULL_UP) # Pin for encoder A
        self.b = Pin(rot_b, mode=Pin.IN, pull=Pin.PULL_UP) # Pin for encoder B
        self.encoder_switch = Pin(e_switch, mode=Pin.IN, pull=Pin.PULL_UP) # Pin for the encoder switch
        
        # Initialize switch pins with pull-up resistors
        self.switch1 = Pin(sw1_pin, mode = Pin.IN, pull = Pin.PULL_UP) # SW1 button
        self.switch2 = Pin(sw2_pin, mode = Pin.IN, pull = Pin.PULL_UP) # SW2 button
        
        # Initialize the ADC for the heart rate sensor
        self.sensor = ADC(Pin(sensor_pin)) # Analog input for the heart rate sensor
        
        # Set up I2C communication for OLED display
        self.i2c = I2C(1, scl=Pin(15), sda=Pin(14), freq=400000) # Initialize I2C for OLED
        self.oled_width = 128 # OLED width
        self.oled_height = 64 # OLED height
        self.oled = SSD1306_I2C(self.oled_width, self.oled_height, self.i2c) # Create OLED object
        
        # Initialize FIFO queues for button, sensor, and encoder events
        self.button_fifo = Fifo(30, typecode='i') # FIFO for button events
        self.sensor_fifo = Fifo(750, typecode='i') # FIFO for sensor readings
        self.encoder_fifo = Fifo(30, typecode='i') # FIFO for encoder events
        
        # Variables to manage debounce for buttons
        self.last_press_time_sw1 = 0 # Last press time for SW_1
        self.last_press_time_sw2 = 0 # Last press time for SW_2
        self.last_press_time_encoder_switch = 0 # Last press time for encoder switch 

        # Set up an interrupt for SW_1 and SW_2 buttons press
        self.switch1.irq(handler=self.button_handler_sw1, trigger=Pin.IRQ_RISING, hard=True) # Set up interrupt for button press
        self.switch2.irq(handler=self.button_handler_sw2, trigger=Pin.IRQ_RISING, hard=True) # Set up interrupt for button press
        
        
        # Set up interrupts for rotary encoder turns and clicks
        self.a.irq(handler=self.turning_encoder_handler, trigger=Pin.IRQ_RISING, hard=True) # Encoder turn event
        self.encoder_switch.irq(handler=self.button_handler_encoder, trigger=Pin.IRQ_RISING, hard=True) # Encoder button press
        
        # Initialize measurement variables
        self.sensor_timer = None # Timer for sensor
        self.option = 0 # Initialize highlighted menu item
        self.measurement_on = False# Flag to indicate if measurement is active
        self.threshold = 0 # Peak detection threshold
        self.thresval = 0.8 # Relative threshold multiplier
        self.max_value = 0 # Maximum sensor value for peak detection
        self.count = 0 # Counter for samples
        self.peaks = [] # List of detected peak positions
        self.hr_values = [] # List of calculated heart rate values
        self.hr_value = 0 # Current heart rate value to display
        self.ppi_intervals = []  # List of Peak-to-Peak Intervals (PPI)
        
        # WiFi and MQTT settings
        self.SSID = "KME751_Group_8"
        self.PASSWORD = "MMN8MMN8"
        self.BROKER_IP = "192.168.8.253"
        self.wlan = None
        #self.connect_wlan() # Connect to WiFi
        self.mqtt_client = None
        
        
        # Variables for storing data and menu states
        self.json_message = {}# To store data in json format to publish 
        self.kubios_response = {}# To store Kubios Cloud analysis response
        self.kubios_measurement = {}# To store Kubios Cloud analysis response for saving and displaying
        self.timestamp = 0
        self.hrv_measurement = {}# To store basic hrv analysis data
        self.history_option = 0  # Selected option in history menu
        self.in_history_menu = False  # Flag to indicate if in history menu
        self.in_history_data = False  # Flag to indicate if viewing history data

        # Initialize OLED live PPG signal variables
        self.PPG_raw = [] # Stores raw sensor data for OLED live PPG signal
        self.PPG_scaled = [-1]*128 # Stores scaled sensor data for OLED live PPG signal
        self.PPG_average = [] # Stores average sensor data for OLED live PPG signal
        self.min_PPG = 0 # Historical min for scaling
        self.max_PPG = 0 # Historical max for scaling
        self.OLED_current_x = 0 # Keeps track of PPG signal between refreshes
  

    def turning_encoder_handler(self, pin):
        # Handler for rotary encoder turn events
        if self.b(): # Check the state of encoder B
            self.encoder_fifo.put(-1) # Put a value to indicate counter-clockwise turn
            
        else:
            self.encoder_fifo.put(1) # Put a value to indicate clockwise turn
            
    def button_handler_encoder(self, pin):
        # Handler for encoder button presses
        current_time = time.ticks_ms() # Get the current time in milliseconds
      
        if current_time - self.last_press_time_encoder_switch > 100:  # Check if the press interval is greater than 100 ms
            self.encoder_fifo.put(2) # Put a value to indicate button press
            self.last_press_time_encoder_switch = current_time # Update last press time
            
    # Interrupt handler for SW_1 button press
    def button_handler_sw1(self, pin):
         # Handler for SW1 button presses
        current_time = time.ticks_ms() # Get the current time in milliseconds

        if current_time - self.last_press_time_sw1 > 100:  # Check if the press interval is greater than 100 ms
            self.button_fifo.put(2) # Put a value to indicate SW_1 press
            self.last_press_time_sw1 = current_time # Update last press time
            
     # Interrupt handler for SW_2 button press
    def button_handler_sw2(self, pin):
         # Handler for SW2 button presses
        current_time = time.ticks_ms() # Get the current time in milliseconds

        if current_time - self.last_press_time_sw1 > 100:  # Check if the press interval is greater than 100 ms
            self.button_fifo.put(3) # Put a value to indicate SW_2 press
            self.last_press_time_sw2 = current_time # Update last press time
            
            
    def display_main_menu(self):
        # Display the menu on the OLED screen
        self.oled.fill(0) # Clear the OLED screen
        
        y_position = 0
        
        options = ["MEASURE HR", "BASIC HRV", "KUBIOS", "HISTORY"]
     
        
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
        lines = [
        "START",
        "MEASUREMENT BY",
        "PRESSING YOUR",
        "FINGER ON THE",
        "SENSOR AND PRESS",
        "THE SW1 BUTTON",
        ]
        # Display each line of instruction text on the OLED
        for i, line in enumerate(lines):
            self.oled.text(line, 0, int(self.oled_height / 2) - 30 + i * 10, 1)
        
        self.oled.show() # Update the OLED display
        
        
    def display_instruction_HR(self):
        # Display instructions for stopping heart rate measurement
        self.oled.fill(0) # Clear OLED screen
        instruction_line1 = "PRESS SW1 BUTTON"
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
    

    def calculate_rmssd(self):
        # Calculate RMSSD (Root Mean Square of Successive Differences)
        differences = [] # List to store successive differences
        for i in range(len(self.ppi_intervals) - 1): 
            difference = self.ppi_intervals[i + 1] - self.ppi_intervals[i] # Calculate the difference between consecutive PPI values
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
        for i in range(len(self.ppi_intervals)):
            difference = m_ppi - self.ppi_intervals[i]
            differences.append(difference ** 2)
        # Calculate the average of the squared differences
        avg_differences = sum(differences) / len(differences)
        
        return int(avg_differences ** 0.5) # Calculate the square root of the average squared difference and return int
    
    
    def get_timestamp(self):
        # Generate a human-readable timestamp from the current time
        ts = time.gmtime()
        self.timestamp = f"{ts[2]}.{ts[1]}.{ts[0]} {ts[3]}:{ts[4]}" # Format as 'DD.MM.YYYY HH:MM'
    

    def calculate_hrv(self):
        # Calculate HRV metrics (mean HR, mean PPI, RMSSD, and SDNN)
        mean_hr = int(sum(self.hr_values) / len(self.hr_values))  # Calculate the mean heart rate
        mean_ppi = int(sum(self.ppi_intervals) / len(self.ppi_intervals)) # Calculate the mean PPI
        rmssd = self.calculate_rmssd() # Calculate RMSSD
        sdnn = self.calculate_sdnn(mean_ppi) # Calculate SDNN
        
         # Store the calculated HRV metrics in a dictionary
        self.hrv_measurement = { 
                        "mean_hr": mean_hr, 
                        "mean_ppi": mean_ppi, 
                        "rmssd": rmssd, 
                        "sdnn": sdnn 
                        }
        
        # Convert the HRV metrics dictionary into a JSON-formatted string
        self.json_message = ujson.dumps(self.hrv_measurement)
     
        self.send_mqtt_message_hrv() # Send the HRV metrics to an MQTT topic
        self.save_data() # Save the HRV metrics to a file
    
    def send_mqtt_message_hrv(self):
        # Publish the HRV metrics to an MQTT broker if the option is in Basic hrv 
        if self.json_message: # Ensure there is data to send
            message = self.json_message
            topic = "project"
            self.mqtt_client.publish(topic, self.json_message) # Publish the message
            print(f"Sending to MQTT: {topic} -> {message}") # print the message being sent
        
    def send_mqtt_message_kubios(self):
        # Publish the HRV metrics to an MQTT broker if the option is in kubios 
        if self.json_message: # Ensure there is data to send
            message = self.json_message
            topic = "kubios-request"
            self.mqtt_client.publish(topic, self.json_message) # Publish the message
            print(f"Sending to MQTT: {topic} -> {message}") # print the message being sent
        
            self.mqtt_client.wait_msg()

   
    def connect_wlan(self):
        # Connecting to the group WLAN
        self.wlan = network.WLAN(network.STA_IF)# Initialize the WLAN interface
        self.wlan.active(True) # Activate the WiFi interface
        self.wlan.connect(self.SSID, self.PASSWORD)  # Connect to the specified network
        
        # Wait until the connection is established
        while self.wlan.isconnected() == False: 
            print("Connecting... ") # print connection attempts
            sleep(1) # Pause briefly between attempts


        # print the successful connection and display the assigned IP address
        print("Connection successful. Pico IP:", self.wlan.ifconfig()[0]) 


    def connect_mqtt_hrv(self):
        # Connect to the MQTT broker if the option is in basic hrv
        self.mqtt_client=MQTTClient("", self.BROKER_IP) # Initialize the MQTT client with the broker IP
        self.mqtt_client.connect(clean_session=True)  # Establish the connection with a clean session

    
    def connect_mqtt_kubios(self):
        # Connect to the MQTT broker if the option is in kubios
        self.mqtt_client=MQTTClient("", self.BROKER_IP, 21883) # Initialize the MQTT client with the broker IP
        self.mqtt_client.set_callback(self.mqtt_callback) # Set the callback function for handling incoming messages
        self.mqtt_client.connect(clean_session=True)  # Establish the connection with a clean session
    
    
    def mqtt_callback(self, topic, msg):
        # This function is the callback to handle incoming MQTT messages.
        self.kubios_response = msg.decode('utf-8') # Store the decoded message in the class variable `kubios_response`.
        self.get_response_data_from_Kubios()  # Call a method to process the received data from Kubios.

    
    def create_kubios_request(self):
        # Subscribe to the response topic to listen for Kubios Cloud's response
        self.mqtt_client.subscribe("kubios-response")
        # Create a dataset for the request, including an ID, type, PPI intervals, and analysis type
        dataset = {
                    "id": 123,
                    "type": "RRI", 
                    "data": self.ppi_intervals, 
                    "analysis": {"type": "readiness"} 
                    }
        # Convert the dataset into a JSON-formatted string for transmission
        self.json_message = ujson.dumps(dataset)
        # Send the created JSON message to Kubios Cloud via MQTT
        self.send_mqtt_message_kubios()
        
    

    def get_response_data_from_Kubios(self):
        if self.kubios_response:
            response = ujson.loads(self.kubios_response) # Parse the analysis results
            # Extract HRV metrics and PNS/SNS values from the response
            mean_hr = int(response["data"]["analysis"]["mean_hr_bpm"])  
            mean_ppi = int(response["data"]["analysis"]["mean_rr_ms"])  
            rmssd = int(response["data"]["analysis"]["rmssd_ms"])      
            sdnn = int(response["data"]["analysis"]["sdnn_ms"])        
            pns = response["data"]["analysis"]["pns_index"]
            sns = response["data"]["analysis"]["sns_index"]
            
            # Assign levels based on PNS and SNS values
            if pns < -1 :
                pns_level = "+"
            elif pns > -1 and pns < 1:
                pns_level = "++"
            elif pns > 1:
                pns_level = "+++"
                
            if sns < -1 :
                sns_level = "+++"
            elif sns > -1 and sns < 1:
                sns_level = "++"
            elif sns > 1:
                sns_level = "+"
            
            # Format the PNS and SNS values to 3 decimal places with their levels
            pns_value = f"{pns:.3f}"
            sns_value = f"{sns:.3f}"

            # Store the results in a dictionary for display and saving
            self.kubios_measurement = {
                                    "mean_hr": mean_hr,
                                    "mean_ppi": mean_ppi,
                                    "rmssd": rmssd,
                                    "sdnn": sdnn,
                                    "pns": pns_value + " " + pns_level,
                                    "sns":  sns_value + " " + sns_level
                                    }
            
            # If the response is valid, display the results and save them to a file
            if self.kubios_response:
                self.display_kubios_response() # Display the Kubios response on the OLED
                self.save_data() # Save the response to a file
        
        
    def save_data(self):
        # Save HRV or Kubios data into a history file with a timestamp
        self.get_timestamp() # Generate a timestamp for the current data entry
        if self.option == 2: # If the Kubios option is selected
            # Prepare data dictionary for Kubios results
            data = {"option": "kubios",
                    "timestamp": self.timestamp,
                    "mean_hr": self.kubios_measurement["mean_hr"],
                    "mean_ppi": self.kubios_measurement["mean_ppi"],
                    "rmssd": self.kubios_measurement["rmssd"],
                    "sdnn": self.kubios_measurement["sdnn"],
                    "pns": self.kubios_measurement["pns"],
                    "sns": self.kubios_measurement["sns"]
                    }
            
        elif self.option == 1: # If the Basic HRV option is selected
            # Prepare data dictionary for basic HRV results
            data = {"option": "basic_hrv",
                    "timestamp": self.timestamp,
                    "mean_hr": self.hrv_measurement["mean_hr"],
                    "mean_ppi": self.hrv_measurement["mean_ppi"],
                    "rmssd": self.hrv_measurement["rmssd"],
                    "sdnn": self.hrv_measurement["sdnn"],
                    }
            
        # Append the new data as a JSON string into the history file
        with open('history.txt', 'a') as file:
            file.write(f"{ujson.dumps(data)}\n")
        
        # Read all lines from the history file to manage its size
        with open('history.txt', 'r') as file:
            lines = file.readlines()
        
        # Limit the history file to the last 3 entries
        if len(lines) > 3:
        
            latest_three = lines[-3:] # Keep the last 3 lines
            
            with open('history.txt', 'w') as file: # Remove all exixting entries
                pass
            
            with open('history.txt', 'r') as file:
                for line in latest_three:
                    file.write(line) # Write back the latest 3 entries
        
        
    def display_kubios_response(self):
        # Display instructions for stopping heart rate measurement
        y_position = 0
        self.oled.fill(0) # Clear OLED screen
        # Prepare response lines for the OLED
        hr_line = f"MEAN HR: {self.kubios_measurement['mean_hr']}"
        ppi_line = f"MEAN PPI: {self.kubios_measurement['mean_ppi']}"
        rmssd_line = f"RMSSD: {self.kubios_measurement['rmssd']}"
        sdnn_line = f"SDNN: {self.kubios_measurement['sdnn']}"
        sns_line = f"SNS: {self.kubios_measurement['sns']}"
        pns_line = f"PNS: {self.kubios_measurement['pns']}"
        # List of lines to display
        response_list = [hr_line, ppi_line, rmssd_line, sdnn_line, sns_line, pns_line]
        
        # Loop through each line and display it on the OLED
        for i in response_list:
            self.oled.text(i, 0, y_position, 1)   
            y_position += 10
            
        self.oled.show() # Update the OLED display
        
        
    
    def display_history_menu(self):
        # Display the history menu on the OLED screen
        self.oled.fill(0) # Clear the OLED screen
        y_position = 0 # Starting vertical position for the menu items
        
        # Instruction texts to be displayed at the bottom of the screen
        instruction_text1 = "PRESS SW2 BUTTON" # Instruction line 1
        instruction_text2 = "TO RETURN" # Instruction line 2
        
        # Open the history file and read its content
        with open('history.txt', 'r') as file:
            lines = file.readlines() # Read all lines from the history file
        
        # Check if the file is empty
        if not lines:
            # If no data is available, display a "No Data" message
            message1 = "NO DATA"
            message2 = "AVAILABLE"
            
            self.oled.text(message1, 0, self.oled_height // 2 - 16, 1)
            self.oled.text(message2, 0, self.oled_height // 2 - 4, 1)
            
        else:
            # If data is available, display the history menu with up to 3 options
            for i in range(min(len(lines), 3)):
                history_option_text= f"MEASUREMENT{i + 1}" # Menu option text
                if i == self.history_option: # Highlight the selected option
                    self.oled.fill_rect(0, y_position, self.oled_width, 8, 1) # Draw highlight rectangle
                    self.oled.text(history_option_text, 0, y_position, 0) # Display highlighted option in black color

                else:
                    self.oled.text(history_option_text, 0, y_position, 1) # Display other options in white color

                y_position += 12 # Move down for the next option
        
        # Add return instructions at the bottom of the screen
        self.oled.text(instruction_text1, 0, 44, 1)
        self.oled.text(instruction_text2, 0, 56, 1)
            
       
        self.oled.show() # Update the OLED display with new content
        
    def display_history(self):
        # Display the selected history entry on the OLED screen
        with open('history.txt', 'r') as file:
            lines = file.readlines() # Read all lines from the history file

       
        data = [ujson.loads(line.strip()) for line in lines] # Parse JSON strings into dictionaries

        history_data = []  # List to hold the main HRV data
        kubios_data = [] # List to hold Kubios-specific data if available

        for i in range(3): # Loop through the 3 saved entries
            if i == self.history_option: # Find the selected history option
                # Extract main HRV data from the entry
                timestamp_line = data[i]["timestamp"]
                mean_hr_line = f"MEAN HR: {data[i]["mean_hr"]}"
                mean_ppi_line = f"MEAN PPI: {data[i]["mean_ppi"]}"
                rmssd_line = f"RMSSD: {data[i]["rmssd"]}"
                sdnn_line = f"SDNN: {data[i]["sdnn"]}"
                history_data = [timestamp_line, mean_hr_line, mean_ppi_line, rmssd_line, sdnn_line]
                
                # If the entry is a Kubios result, extract additional data
                if data[i]["option"] == "kubios":
                    sns_line = f"SNS: {data[i]["sns"]}"
                    pns_line = f"PNS: {data[i]["pns"]}"
                    kubios_data = [sns_line, pns_line]
                    history_data.extend(kubios_data) # Add Kubios data to the main history data
                    
        self.oled.fill(0) # Clear OLED screen
        y_position = 0 # Starting vertical position for the history data
        
        # Loop through the collected history data and display it
        for i in history_data:
            self.oled.text(i, 0, y_position, 1) # Add text to the OLED 
            y_position += 9 # Move to the next line
            
        self.oled.show() # Update the OLED display
        
    def scale_PPG_value(self, value): 
        scaledValue = 63 - (value - self.min_PPG)*(63 / (self.max_PPG - self.min_PPG)) # Scale the PPG value
        if scaledValue < 0: # Ensure the value is within the OLED range
            scaledValue = 0
        elif scaledValue > 63: 
            scaledValue = 63
        return int(scaledValue) # Return the scaled value
    
    def update_min_max_for_scaling(self, rawData):
        # Try different ways: average vs not
        if True:
            # Calculate the average of every 5 consecutive values
            averaged_data = [sum(rawData[i:i+5]) / 5 for i in range(0, len(rawData), 5) if len(rawData[i:i+5]) == 5]
            
            # Update min and max values based on the averaged data
            self.min_PPG = min(averaged_data) if averaged_data else None
            self.max_PPG = max(averaged_data) if averaged_data else None
        else:
            self.min_PPG = min(rawData)
            self.max_PPG = max(rawData)

    def delete_trail(self):
        # Delete the trail of the PPG signal
        for i in range(8):
            index = (self.current_x + i) % 128  # Calculate the index with wrap-around
            self.oled.pixel(index, self.PPG_scaled[index], 0)  # Clear the pixel on the OLED screen
    
    def update_live_PPG(self, sampleValue):
        self.PPG_raw.append(sampleValue) # Stores raw sensor data for OLED live PPG signal
        multiplier = 3 # Multiplier for number of samples to collect for min and max

        if len(self.PPG_raw) == (multiplier*128): # Update min and max values every x samples
            self.update_min_max_for_scaling(self.PPG_raw) # Update min and max values for scaling
            self.PPG_raw = [] # Clear the raw sensor data list
            
        if self.max_PPG == 0:
            return
        
        self.PPG_average.append(sampleValue) # Stores average sensor data for OLED live PPG signal
        
        averaging_multiplier = 10
        if len(self.PPG_average) == averaging_multiplier: # Update averaging last x samples
            sampleValue = sum(self.PPG_average) // len(self.PPG_average)
            self.PPG_average.pop(0)
        else:
            return

        self.current_x = self.OLED_current_x % 128 # Calculate the current x position with wrap-around
        self.PPG_scaled[self.current_x] = self.scale_PPG_value(sampleValue) # Scale the PPG value
        self.OLED_current_x += 1
        
        #print((self.current_x-1), len(self.PPG_scaled), self.scale_PPG_value(sampleValue))
        # update OLED every x new values
        if (self.OLED_current_x % 5) != 0:
            return
        
        self.oled.fill(0) # Clear the OLED screen
        for index, value in enumerate(self.PPG_scaled): # Draw the PPG signal on the OLED
            if value == -1:
                continue
            self.oled.pixel(index, value, 1) # Draw a pixel at the scaled PPG value

        self.delete_trail() # Delete the trail of the PPG signal
        self.oled.show()
    
    def reset_PPG_variables(self):
        # Reset variables after measurement
        self.PPG_raw = [] # Stores raw sensor data for OLED live PPG signal
        self.PPG_scaled = [-1]*128 # Stores scaled sensor data for OLED live PPG signal
        self.PPG_average = [] # Stores average sensor data for OLED live PPG signal
        self.min_PPG = 0 # Historical min for scaling
        self.max_PPG = 0 # Historical max for scaling
        self.OLED_current_x = 0 # Keeps track of PPG signal between refreshes
    
    def show_collecting_data(self):
        self.oled.fill(0)
        text_1 = "COLLECTING"
        text_2 = "DATA..."
        text_y_1 = 63//2 - 10
        text_y_2 = text_y_1 + 10
        text_x_1 = 23
        text_x_2 = text_x_1 + 16
        self.oled.text(text_1, text_x_1, text_y_1)
        self.oled.text(text_2, text_x_2, text_y_2)
        self.oled.show()
        
    def show_sending_data(self):
        self.oled.fill(0)
        text = "SENDING DATA..."
        text_y = 63//2 - 4
        text_x = 10
        self.oled.text(text, text_x, text_y)
        self.oled.show()
        
# Instantiate the Pico class with appropriate GPIO pin numbers
# sw1_pin=8, sensor_pin=27, rot_a=10, rot_b=11, e_switch=12
pico = Pico(7, 8, 27, 10, 11, 12)

# Display the main menu on the OLED screen
pico.display_main_menu()

# Main loop to process events and update heart rate
while True:
    # Handle events from the rotary encoder (turns and button press)
    if pico.encoder_fifo.has_data():
        encoder_data = pico.encoder_fifo.get() # Get the data from the FIFO
        
        if encoder_data == 2: # If the encoder button is pressed
            if not pico.in_history_menu: # If not in the history menu
                if pico.option == 3:  # If the History option is selected
                    pico.in_history_menu = True # Enter the history menu
                    pico.display_history_menu()  # Display the history menu
                else: # For other menu options
                    pico.display_instruction1()  # Show the instructions for starting measurement
            
            else: # If already in the history menu
                pico.display_history() # Display the selected history data
                pico.in_history_data = True # Mark that history data is being displayed
     
        
        if encoder_data == -1: # Check for counter-clockwise turn event
            if pico.in_history_menu: # If in the history menu
                if pico.history_option > 0: # Ensure it doesn't go out of bounds
                    pico.history_option -= 1 # Move the selection up
                    pico.display_history_menu() # Update the history menu display
            else: # If in the main menu
                if pico.option > 0: # Ensure it doesn't go out of bounds
                    pico.option -= 1 # Move highlight up in the menu
                    pico.display_main_menu() # Update the menu display
                
        elif encoder_data == 1:  # Check for clockwise turn event
            if pico.in_history_menu: # If in the history menu
                if pico.history_option < 2: # Ensure it doesn't go out of bounds
                    pico.history_option += 1 # Move the selection up
                    pico.display_history_menu() # Update the history menu display
            else: # If in the main menu
                if pico.option < 3:  # Ensure it doesn't exceed the menu options
                    pico.option += 1 # Move highlight down in the menu
                    pico.display_main_menu() # Update the menu display
        
    # Handle events from the SW1 button
    if pico.button_fifo.has_data(): # Check if there are any events in the button FIFO
        button_data = pico.button_fifo.get() # Get the data from the FIFO queue

        if button_data == 2: # If SW_1 button press is detected
            if pico.option != 3: # If not in the History option
                if pico.measurement_on: # If measurement is currently active
                    pico.count = 0 # Reset the sample counter
                    pico.measurement_on = False # Stop measurement
                    pico.option = 0 # Reset the menu option
                    pico.display_main_menu() # Return to the main menu
                    pico.peaks = [] # Clear the list of detected peaks
                    pico.hr_values = []  # Clear the heart rate values
                    pico.empty_sensor_fifo() # Clear FIFO
                    pico.ppi_intervals = [] # Clear the PPI values
                    pico.hrv_measurement = {} # Clear HRV measurement
                    pico.kubios_response = {} # Clear Kubios response data
                    pico.json_message = {}#Clear json format data
                    if pico.sensor_timer:  # Check if sensor_timer exists
                        pico.sensor_timer.deinit()  # Stop the sensor_timer
                        pico.sensor_timer = None  # Reset sensor_timer reference
 
                        
                        
                else: # If measurement is not currently active
                    if pico.option == 1:
                        pico.connect_mqtt_hrv()# Connect to the MQTT broker for HRV (Heart Rate Variability) analysis
                    elif pico.option == 2:
                        pico.connect_mqtt_kubios() # Connect to the MQTT broker for Kubios Cloud analysis
                    pico.set_sensor_timer() # Start the sensor timer
                    pico.measurement_on = True # Start measurement
                    

        if button_data == 3: # If SW2 button press is detected       
            if pico.option == 3: # If in the History option
                if not pico.in_history_data: # If not viewing history data
                    pico.option = 0 # Reset the menu option
                    pico.display_main_menu() # Return to the main menu
                    pico.in_history_menu = False # Exit the history menu
                else: # If viewing history data
                    pico.history_option = 0 # Reset the history option
                    pico.display_history_menu() # Return to the history menu
                    pico.in_history_data = False # Exit the history data view
                     
                
    # Handle sensor data processing    
    if pico.sensor_fifo.has_data(): # Check if there is data in the FIFO
        sample = pico.sensor_fifo.get() # Get the data from the FIFO
        
        if pico.measurement_on == True:
            
                
            
            pico.count += 1 # Increment the sample counter
            
            # Draw to OLED with scaling based on previous 125 samples
            
            if pico.count == 1: # On the first sample
                pico.display_instruction_HR() # Show stop instructions
            
            if pico.count < 1000: # Ignore the first 1000 samples (initial noise)
                pico.empty_sensor_fifo()  # Clear the FIFO to discard noisy data

            if pico.count >= 1250: # Start processing data after the initial noise is ignored
                if pico.count == 1250 or pico.count % 125 == 0:  # Set threshold periodically
                    pico.set_threshold()# Set threshold for peak detection
                    
                if pico.option == 0: # If in the HR measurement mode
                    pico.update_live_PPG(sample) # Update the live PPG signal on the OLED
                
                pico.detect_peaks(sample)# Detect peaks
                    
                if pico.count % 500 == 0: # Every 500 samples
                    pico.calculate_hr() # Calculate heart rate

                elif pico.option == 1 and not pico.hrv_measurement: # If in HRV analysis mode
                    if pico.count > 8750: # Process HRV metrics after sufficient data is collected

                        if pico.sensor_timer:  # Check if sensor_timer exists
                            pico.sensor_timer.deinit()  # Stop the sensor_timer
                            pico.sensor_timer = None  # Reset sensor_timer reference
                        
                        pico.calculate_hrv() # Calculate HRV metrics (Mean HR, Mean PPI, RMSSD, SDNN)
     

                elif pico.option == 2: # If in Kubios analysis mode
                    if pico.count > 8750 and len(pico.ppi_intervals) > 15 and not pico.json_message:
                        if pico.sensor_timer:  # Check if sensor_timer exists
                            pico.sensor_timer.deinit()  # Stop the sensor_timer
                            pico.sensor_timer = None  # Reset sensor_timer reference

                        pico.create_kubios_request() # Send data to Kubios and process the response
                        
               
