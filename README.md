# Raspberry Pi Pico Heart Rate Monitor

This project implements a heart rate monitoring system using Raspberry Pi Pico.  
It measures and displays BPM with a PPG sensor, rotary encoder, buttons, and OLED screen.  

Features include:
- Real-time BPM measurement with ±10% accuracy (validated against a pulse oximeter)  
- User-friendly menu with HRV analysis (mean PPI, RMSSD, SDNN)  
- Wi-Fi connectivity with MQTT for remote monitoring  
- Options to view live PPG signals, save historical data, and integrate with Kubios software  

Built with MicroPython on Thonny IDE, this system demonstrates a multifunctional health tech device that is reliable, accurate, and easy to use.  
This project was developed as part of a first-year hardware course at Metropolia University of Applied Sciences.

## Software & Tools
- **MicroPython**: Program code executed through Pico firmware  
- **Thonny IDE**: Development and debugging environment for Raspberry Pi Pico  
- **SSD1306 Library**: OLED display control  
- **MQTT Library**: Data transmission to a client laptop via Raspberry Pi-based broker  
- **Kubios Cloud API**: Advanced HRV analysis using collected PPI data
  
### System Diagram for Heart Rate Detection and Analysis System 
<img width="596" height="406" alt="image" src="https://github.com/user-attachments/assets/61ca1659-1d85-4b1b-8798-f22e00881fa2" />

### Main Menu of the System
<img width="279" height="160" alt="image" src="https://github.com/user-attachments/assets/44d4b4dc-2303-401f-994c-a404a05310b4" />

### The live PPG signal waveform and the calculated heart rate value
<img width="268" height="152" alt="image" src="https://github.com/user-attachments/assets/14821856-cdfd-4a84-98f9-d307bf426329" />

### Kubios HRV Results Displayed on the OLED Screen
<img width="283" height="152" alt="image" src="https://github.com/user-attachments/assets/81b271cd-2cba-4f07-b094-61c67e3b46eb" />



 
