# Zehnder ComfoAir E300/E400 Home Assistant Integration


## Installation integration

### HACS Custom Repository

1. Open HACS in Home Assistant.
2. Click the three dots menu (⋮) in the top right corner.
3. Select 'Custom repositories'.
4. Add this repository URL: `https://github.com/remmob/comfoair`.
5. Set the category to **Integration**.
6. Click 'Add' to save.

See the [official HACS documentation](https://hacs.xyz/docs/faq/custom_repositories/) for more details.

### Manual

1. Download or copy the `comfoair` folder from this repository:
	[`custom_components/comfoair`](../itho_amber)
2. Place this folder in your Home Assistant installation under:
	`config/custom_components/comfoair`
3. Restart Home Assistant.
4. Add the integration via the Integrations screen in the Home Assistant UI.

More info and updates:
- [GitHub: remmob/comfoair](https://github.com/remmob/comfoair)



## Hardware Requirements
This integration uses modbus to connect to the Zehnder E300/E400 unit.

![Display](images/display.png)

You can use a USB to RS485 adapter to connect to the unit. The adapter should be connected to the Modbus port on the unit.<br/>
A+ to A and B- to B, if you receive no data, try to swap the A and B wires.
<br/>Or alternatively, you can use a WiFi/Ethernet to RS485 gateway, which allows you to connect to the unit wirelessly or ethernet. 
Like a Elfin EW-11

> ## Important!<br/> 
>Do not use the 12V of the Zehnder unit to power your gateway or wifi device. It can not provide enough power and can damage your device. Use a separate power supply for your gateway or wifi device.<br/><br/>
 
 The integration suports both Modbus RTU (via USB) and Modbus TCP (via WiFi/Ethernet).
<br/>Go to the Integrations page in Home Assistant and click on "Add Integration". Search for "Zehnder ComfoAir" and select it.

 ![start](images/start.png)

 To identify this unit, you have to give it a name (default: "zehnder") 
 The device ID cannot be changed and should be set to 1
 and select the connection type (RTU or TCP).

 ![RTU](images/rtu.png)
 
 The available serial ports on your system will be listed.
 Sins there is no way to change the connection settings, those are fixed and cannot be changed. The default settings are:
- Baudrate: 19200
- parity: Even
- stopbits: 1
- bytesize: 8

For TCP connection, you need to provide the IP address and port of the Modbus TCP gateway. The default port is 502.
In your modbus RTU to TCP gateway you need to set the above connection settings.

![TCP](images/tcp.png)

Last step is to select the type of unit RF, Analog, or 3-way switch. This will determine which registers are activated The registers of the not used type will be available but deactivated. <br/>You can change the type of unit later in the settings of the integration. <br/><br/>
![control](images/control.png)

All settings can be reconfigured in the Comfoair device page
[https://yourhomeassistanturl:8123/config/integrations/integration/comfoair](https://yourhomeassistanturl:8123/config/integrations/integration/comfoair)


## Register Table

| Register | Name                                         | Datatype | Unit   | Scale | Note                                  |
|----------|----------------------------------------------|----------|--------|-------|---------------------------------------|
| 110      | Software version                             | uint16   | -      | 1     | 20800 = 2.8.0 (firmware)              |
| 300      | Intake Air Temperature                       | int16    | °C     | 0.1   |                                       |
| 301      | Pre-heater temperature                       | int16    | °C     | 0.1   |                                       |
| 303      | Supply air temperature                       | int16    | °C     | 0.1   |                                       |
| 304      | Extract air temperature                      | int16    | °C     | 0.1   |                                       |
| 305      | Exhaust air temperature                      | int16    | °C     | 0.1   |                                       |
| 306      | Supply Air Humidity                          | uint16   | %      | 0.1   |                                       |
| 307      | Exhaust Air Humidity                         | uint16   | %      | 0.1   |                                       |
| 308      | Extract Air Humidity                         | uint16   | %      | 0.1   |                                       |
| 309      | Intake Air Humidity                          | uint16   | %      | 0.1   |                                       |
| 318      | RF Enabled                                   | uint16   | -      | 1     |                                       |
| 319      | Pre-heater state                             | uint16   | -      | 1     |                                       |
| 320      | Extract Air Flow setpoint +- balance offset  | uint16   | m³/h   | 1     |                                       |
| 321      | Supply Air flow setpoint                     | uint16   | m³/h   | 1     |                                       |
| 328      | 0-10 V speed setting                         | uint16   | %      | 1     | 0:low;50:medium;100:high              |
| 329      | RF speed setting                             | uint16   | %      | 1     | 0:low;50:medium;100:high              |
| 330      | 3-way switch                                 | uint16   | %      | 1     | 0:low;50:medium;100:high              |
| 336      | Runtime in days                              | uint16   | days   | 1     |                                       |
| 337      | Fireplace mode On/Off                        | uint16   | -      | 1     |                                       |
| 338      | Pre-Heater On/Off                            | uint16   | -      | 1     |                                       |

**Datatype**: uint16 = unsigned 16-bit, int16 = signed 16-bit

**Scale**: Value must be multiplied by this factor for real-world value.


# Roadmap
- Add automation for sending filter replacement notifications.
- Add automation on connection loss.