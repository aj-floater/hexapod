# Hexapod Project — Literature Report

- Closed-loop Smart Servo: surveying open smart‑servo designs (STM32-based, I2C feedback, PID + filtering), with quick notes on SG90 suitability and adaptation path.
- Integrated BMS: outlining a 2S 18650 USB‑C PD power path (PD controller → buck‑boost charger → primary/secondary protection + balancing) with candidate ICs and datasheets.

# Closed-loop Smart Servo Research

## STM32-Powered Board Turns Hobby Servos Into Smart Servos

- External PCB adds: added PID control and low-pass filtering to achieve smooth, vibration-free movement
- supports I2C communication, allowing you to read the current angle, speed output, and more from the servo motor. 
- You can also set the maximum torque and adjust the gains of the low-pass filter and PID controller

- Sources:
  - [KoshiroRobot/Simple-Smart-Servo-Driver](https://github.com/KoshiroRobot/Simple-Smart-Servo-Driver)
  - [Hackster](https://www.hackster.io/news/koshiro-robot-creator-s-stmicro-stm32-powered-board-turns-hobby-servos-into-smart-servos-e0efcf5b4073?utm_source=chatgpt.com): STM32-powered board turns hobby servos into smart servos

- Personal notes:
  - The best option I have
  - It explicitly makes use of the SG90s servo (the one that I will be using)
  - Currently built for use with a Raspberry Pi/Linux computer, but definitely could be modified for use with Arduino
  - Includes a detailed explainer of the system, including the PID loop, all in video format

## LibreServo v2

- open design to convert any hobby servo into a smart servo
- Compatible with standard servo motors
- Communications: RS-485 half-duplex
- Micro-Controller: STM32F301k8
- Position sensor: Magnetic encoder, 16 bits of resolution! 360 degrees (AEAT-8800). Using the servo motor potentiometer will be possible to lower the cost but will lost precision and some characteristics.

- Sources:
  - [LibreServo v2 GitHub](https://github.com/Luisonson/LibreServo_v2?utm_source=chatgpt.com)
  - [libreservo.com](https://www.libreservo.com/en)

- Personal notes:
  - Looks to be just a PCB design at the moment
  - Useful for understanding the process
  - Doesn't make specific use of the SG90 servo motor

## Servio

- Servio is an open-source servo design that includes firmware code and a custom controller PCB design
- Most recent update shows that PCB fitting into a Hiwonder LX-15D servo motor enclosure (with a custom 3D-printed cover), but the same PCB should work for many other designs and sizes—or completely custom servo enclosures

- Sources:
  - [Build smarter servos with Servio (Hackster)](https://www.hackster.io/news/build-smarter-servos-with-servio-3a849f71ff56?utm_source=chatgpt.com)

- Personal notes:
  - The currently used servo is a bit too bulky and expensive, but design ideas could be useful

# Integrated BMS Research

- USB-C Power Delivery controller negotiates suitable input voltage/current from the charger brick
- That input then feeds a buck-boost multi-cell charger configured for a 2-cell Li-ion pack
- On the battery side, add a primary protection IC which monitors both cells and disconnects the pack for overcharge, over-discharge, or over-current faults
- Secondary protection/balancer to provide precise over-voltage back-stop and automatic cell balancing so series cells stay equalized

## USB-C PD
- TI [TPS25750](https://www.ti.com/product/TPS25750) – stand-alone PD controller w/ power paths & charger control.
  - [TPS25751 datasheet](https://www.ti.com/lit/ds/symlink/tps25751.pdf) 

## Charging IC's
- [MAX77962](https://www.analog.com/en/products/max77962.html) buck-boost 2-cell charger (3.5–23 V in), designed for USB-C. Great fit for 2S
  - [MAX77962 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/max77962.pdf)

- TI [BQ25700A](https://www.ti.com/product/BQ25700A) buck-boost charger
  - [BQ25700A datasheet](https://www.ti.com/lit/ds/symlink/bq25700a.pdf)

## Battery Protection
- S-8252 Primary pack protector (2S): dedicated IC that monitors both cells `primary`
  - [S-8252 datasheet](https://www.ablic.com/en/doc/datasheet/battery_protection/S8252_E.pdf)
- TI [BQ29200](https://www.ti.com/product/BQ29200)/[BQ29209](https://www.ti.com/product/BQ29209) – 2S OVP + auto-balancing `secondary`
  - [BQ29200 datasheet](https://www.ti.com/lit/ds/symlink/bq29200.pdf)
