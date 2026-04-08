# Known Hexapod Platforms — Research Findings

Compiled for literature review: compact servo driver board with per-joint closed-loop control and simulation-based feedforward for a small hexapod robot.

---

## RHex

**Origin:** University of Michigan / McGill University (joint project; Koditschek lab at Michigan, Buehler lab at McGill)
**Year:** 2001 (primary IJRR publication)
**Citation:** Saranli, U., Buehler, M., and Koditschek, D. E. (2001). "RHex: A Simple and Highly Mobile Hexapod Robot." *The International Journal of Robotics Research*, 20(7), 616–631. DOI: 10.1177/02783640122067570

### Physical
- Mass: approximately 9 kg (with batteries)
- Body dimensions: 53 cm (L) × 20 cm (W) × 15 cm (H); leg length ~17.5 cm
- DOF/leg: 1 (single hip rotation — leg rotates full circle)
- Total actuators: 6 (one brushed DC motor per hip)
- Actuator type: Maxon RE11875 brushed DC motor with Maxon 33:1 two-stage planetary gearhead; 20 W continuous, 24 V supply; stall torque ~6 Nm

### Electronics & Communication
- Architecture: Centralised PC104 stack onboard — 100 MHz Intel 486 processor with I/O boards for motor drive and encoder reading; two 12 V 2.2 Ah Panasonic sealed lead-acid batteries; all computation and motor control self-contained on body
- Interface: Internal bus (PC104 bus); PWM motor commands to H-bridge drivers; quadrature encoder feedback per joint; no external wireless during experiments in primary paper

### Locomotion & Control
- Gaits demonstrated: Clock-driven open-loop alternating tripod gait; passive compliant leg spring stores and returns energy analogous to SLIP model
- Terrain: Rubble, grass, gravel, rocky ground, stair-like obstacles exceeding body clearance; traverses height variations greater than ground clearance
- Speed: Up to ~0.5 m/s (approximately one body length per second)
- Control approach: Task-space open-loop (no external sensing for body-state estimation); joint-space proprioceptive closed-loop using encoder feedback to regulate hip rotation rate; compliant C-shaped legs provide passive mechanical compliance — no active leg-tip force or impedance control

### Key gap / limitation
RHex deliberately limits each leg to 1 DOF to achieve mechanical simplicity; there is no per-joint position or torque servo at any intermediate limb segment. The clock-driven open-loop gait requires careful hand-tuning of timing parameters and leg stiffness; there is no adaptive feedforward or model-based compensation per joint. Gain tuning is global (one clock parameter set) rather than per-joint, and position tracking quality at each hip depends entirely on a single speed-regulated motor with encoder rather than a dedicated servo controller with programmable PID gains. The platform is not designed for fine-grained per-joint position servo work.

### Suggested BibTeX entry
```bibtex
@article{saranli2001rhex,
  author    = {Saranli, Uluc and Buehler, Martin and Koditschek, Daniel E.},
  title     = {{RHex}: A Simple and Highly Mobile Hexapod Robot},
  journal   = {The International Journal of Robotics Research},
  volume    = {20},
  number    = {7},
  pages     = {616--631},
  year      = {2001},
  doi       = {10.1177/02783640122067570}
}
```

---

## AMOS-II

**Origin:** Bernstein Center for Computational Neuroscience / University of Göttingen, Germany; later continued at University of Southern Denmark (SDU), Manoonpong lab
**Year:** 2008 (primary journal publication); platform first described ~2006
**Citation:** Manoonpong, P., Pasemann, F., and Wörgötter, F. (2008). "Sensor-driven neural control for omnidirectional locomotion and versatile reactive behaviors of walking machines." *Robotics and Autonomous Systems*, 56(3), 265–288. DOI: 10.1016/j.robot.2007.07.004

Also widely cited for obstacle negotiation work: Goldschmidt, D., Wörgötter, F., and Manoonpong, P. (2014). "Biologically-inspired adaptive obstacle negotiation behavior of hexapod robots." *Frontiers in Neurorobotics*, 8, 3. DOI: 10.3389/fnbot.2014.00003

### Physical
- Mass: approximately 5.4 kg (56.9 N weight reported)
- Body dimensions: Not reported explicitly; body split into two segments connected by a backbone joint (BJ)
- DOF/leg: 3 (TC: thoraco-coxal forward/backward; CTr: coxa-trochanteral elevation/depression; FTi: femur-tibia extension/flexion)
- Total actuators: 19 (18 leg joints + 1 backbone joint)
- Actuator type: DC servomotors, stall torque 2.9 Nm at 5 V, operated in position control mode; specific model not stated in accessible sources

### Electronics & Communication
- Architecture: Centralised control PC connected via serial interface; neural control network runs off-board on a PC (or embedded controller); sensors include 2 ultrasonic sensors, 6 foot contact sensors, 6 infrared reflex sensors, current sensor, inclinometer, 3 LDRs, USB camera, laser scanner (21 sensors total)
- Interface: Serial (RS-232 or USB) connection to host PC; servos addressed individually in position mode

### Locomotion & Control
- Gaits demonstrated: Wave gait, tetrapod, caterpillar, tripod; omnidirectional walking (forward, backward, sideways, turning); obstacle climbing up to 13 cm (75 % of leg length in real environment, 85 % in simulation)
- Terrain: Flat indoor surfaces; obstacles; rough terrain experiments
- Control approach: Biologically-inspired neural control: neuromodulated CPG (central pattern generator) produces periodic leg-drive signals; motor control networks (phase switching network, velocity regulating networks) modulate CPG output for omnidirectional motion; local leg reflexes handle ground contact; neural learning (input correlation learning / classical conditioning) adapts obstacle negotiation to variable conditions — no model-based feedforward

### Key gap / limitation
All servo joints are operated in position mode with fixed internal PID gains inside each servo — there is no exposed per-joint gain tuning, no torque feedback, and no compliance control. The neural CPG approach is computationally expensive and slow to adapt (learning convergence times extend significantly for higher obstacles and faster gaits; some parameter combinations fail to converge). The electronics architecture relies on a tethered or onboard serial link to a host PC; the servo position control quality is limited by the closed-box servo internals with no user-accessible impedance or torque control loop.

### Suggested BibTeX entry
```bibtex
@article{manoonpong2008sensordriven,
  author    = {Manoonpong, Poramate and Pasemann, Frank and W{\"o}rg{\"o}tter, Florentin},
  title     = {Sensor-driven neural control for omnidirectional locomotion and versatile reactive behaviors of walking machines},
  journal   = {Robotics and Autonomous Systems},
  volume    = {56},
  number    = {3},
  pages     = {265--288},
  year      = {2008},
  doi       = {10.1016/j.robot.2007.07.004}
}

@article{goldschmidt2014amosii,
  author    = {Goldschmidt, Dennis and W{\"o}rg{\"o}tter, Florentin and Manoonpong, Poramate},
  title     = {Biologically-inspired adaptive obstacle negotiation behavior of hexapod robots},
  journal   = {Frontiers in Neurorobotics},
  volume    = {8},
  pages     = {3},
  year      = {2014},
  doi       = {10.3389/fnbot.2014.00003}
}
```

---

## LAURON V

**Origin:** FZI Forschungszentrum Informatik (FZI Research Center for Information Technology), Karlsruhe, Germany; affiliated with Karlsruhe Institute of Technology (KIT)
**Year:** 2014 (primary conference paper at IEEE/ASME AIM); robot series started ~1993
**Citation:** Roennau, A., Heppner, G., Nowicki, M., and Dillmann, R. (2014). "LAURON V: A Versatile Six-Legged Walking Robot with Advanced Maneuverability." *Proc. IEEE/ASME International Conference on Advanced Intelligent Mechatronics (AIM)*, Besançon, France, pp. 82–87. DOI: 10.1109/AIM.2014.6878051

### Physical
- Mass: approximately 42 kg (including batteries); payload capacity ~12 kg
- Body footprint: approximately 0.9 m × 0.8 m in default standing position; maximum height ~0.83 m with PTU sensor head
- DOF/leg: 4 (three standard insect-like joints + one additional proximal rotational joint for enhanced workspace; 26 DOF total across six legs plus head/PTU)
- Total actuators: 24 leg joints + head/PTU actuators (~26 total active DOF)
- Actuator type: Faulhaber 2657 012CR brushed DC motors with Faulhaber 26/1S planetary gearheads (gear ratios 66:1 and 159:1 depending on joint)

### Electronics & Communication
- Architecture: Distributed per-leg microcontroller architecture — 9 custom UCoM (Universal Controller Module) boards, each combining a DSP and FPGA; each UCoM handles real-time joint-level PID control, quadrature encoder readout, current measurement, and CAN bus communication; the UCoMs are connected to a central main computer via CAN bus. Main computer: Mini-ITX board (GIGABYTE GA-H87N-Wifi) with Intel Core i7 (4×3.0 GHz), 8 GB RAM. Additional boards: Arduino for auxiliary I/O, Raspberry Pi for 3D laser scanner
- Interface: CAN bus (per-leg UCoMs to main PC); internal DSP/FPGA per UCoM handles PWM drive to DC motors and encoder counting

### Locomotion & Control
- Gaits demonstrated: Statically stable insectoid and mammalian leg configurations; wave gait, tripod gait; terrain-adaptive reactive behaviours (obstacle stepping, posture control)
- Terrain: Rough outdoor terrain, slopes, rocky ground, forest environments; designed for search-and-rescue and inspection tasks
- Speed: Not found in accessible sources for LAURON V specifically; LAURON IV achieved up to 0.22 m/s
- Control approach: Hierarchical behaviour-based control system; high-level behaviour blocks produce setpoints; per-leg behaviour groups (swing, stance, ground contact, collision reflexes) govern step timing; low-level PID joint controllers run on UCoM DSPs; robot operates without terrain sensing relying on reactive posture compensation

### Key gap / limitation
The distributed UCoM architecture is a bespoke custom hardware development, making it difficult to replicate or adapt. Each UCoM board runs per-joint PID but gain calibration across 24+ motors is a significant engineering effort. The platform is very large (42 kg) and expensive, unsuitable as a small-scale hexapod. While per-leg distributed control exists, the communication is CAN bus at relatively modest rates, and the position control loop quality depends on manual encoder-based PID tuning without automatic identification or feedforward compensation. LAURON VI moved to ANYbotics series-elastic actuators and EtherCAT, indicating the LAURON V brushed-DC/UCoM stack was a recognised bottleneck.

### Suggested BibTeX entry
```bibtex
@inproceedings{roennau2014lauronv,
  author    = {Roennau, Arne and Heppner, Georg and Nowicki, Marius and Dillmann, R{\"u}diger},
  title     = {{LAURON V}: A Versatile Six-Legged Walking Robot with Advanced Maneuverability},
  booktitle = {Proceedings of the IEEE/ASME International Conference on Advanced Intelligent Mechatronics (AIM)},
  pages     = {82--87},
  year      = {2014},
  address   = {Besan\c{c}on, France},
  doi       = {10.1109/AIM.2014.6878051}
}
```

---

## PhantomX Hexapod (Mark III)

**Origin:** Trossen Robotics (Interbotix Labs), Vernon Hills, Illinois, USA — commercial hobbyist/education kit
**Year:** 2011 (original PhantomX launch); Mark III revision released later; product not associated with a primary academic publication
**Citation:** Trossen Robotics / Interbotix Labs. (2011). *PhantomX AX Metal Hexapod*. Product page: https://www.trossenrobotics.com/phantomx-ax-hexapod.aspx. Blog announcement: http://blog.trossenrobotics.com/2011/01/12/phantomx-hexapods-have-arrived/

### Physical
- Mass: approximately 2.1 kg (4.6 lbs) without payload; payload capacity ~2 kg (4.4 lbs)
- Body dimensions: approximately 48 cm (L) × 51 cm (W) × 19–23 cm (H) standing; exact body frame dimensions not stated
- DOF/leg: 3 (coxa, femur, tibia)
- Total actuators: 18 Dynamixel AX-12A smart servos (3 per leg × 6 legs)
- Actuator type: Robotis Dynamixel AX-12A — smart serial servo; built-in position, speed, load, voltage, temperature feedback; stall torque 1.5 Nm at 12 V; no-load speed 59 rpm at 12 V; mass 54.6 g per servo

### Electronics & Communication
- Architecture: Single centralised ArbotiX-M Robocontroller board (AVR ATmega2560 microcontroller, Arduino-compatible); runs IK and gait engine onboard; all 18 servos addressed from one board via a daisy-chained TTL serial bus; XBee radio module fitted for wireless command link to handheld ArbotiX Commander
- Interface: Dynamixel TTL half-duplex asynchronous serial bus at up to 1 Mbps (shared bus, all 18 servos on one chain); XBee 2.4 GHz wireless for user remote control; USB/FTDI for programming

### Locomotion & Control
- Gaits demonstrated: 6 preloaded gaits (tripod, ripple, wave, and variants); omnidirectional walking, turning; speed reportedly near 1 m/s at maximum
- Terrain: Flat and mildly uneven indoor surfaces; not designed for rough terrain
- Control approach: Centralised inverse kinematics and gait engine running on ATmega2560 (Vanadium Labs NUKE engine); each Dynamixel servo implements its own internal position PID loop with user-programmable compliance slope and margin (approximate PID equivalent); no torque or force feedback used at system level; essentially open-loop at gait level with per-servo closed-loop position control

### Key gap / limitation
All 18 servos share a single TTL serial bus: at 1 Mbps with 18 servos polled for position plus commands sent, the effective per-servo update rate is limited (typically 50–100 Hz loop rate is reported in practice). The AX-12A compliance/PID parameters are coarse (8-bit resolution compliance slope), making fine per-joint gain tuning difficult. There is no torque sensing, no impedance control, and no feedforward compensation — the system is purely reactive position servo. The centralised ATmega2560 lacks the computational headroom for model-based or simulation-based control. The platform is explicitly a low-cost hobbyist kit, not designed for research-grade actuation quality.

### Suggested BibTeX entry
```bibtex
@misc{trossenrobotics2011phantomx,
  author       = {{Trossen Robotics / Interbotix Labs}},
  title        = {{PhantomX AX Metal Hexapod}},
  year         = {2011},
  howpublished = {Product, \url{https://www.trossenrobotics.com/phantomx-ax-hexapod.aspx}}
}
```

---

## HEBI Robotics Daisy Hexapod

**Origin:** HEBI Robotics, Pittsburgh, PA, USA (founded by Prof. Howie Choset, Carnegie Mellon University Robotics Institute)
**Year:** 2017 (public debut at Robot Revolution exhibit, Chicago Museum of Science and Industry, May 2017); X-Series actuator platform developed from ~2015
**Citation:** No single primary academic paper for Daisy as a platform. Hardware described via product documentation. Frequently cited in context of: HEBI Robotics. (2017). *Daisy 18-DoF Hexapod Kit*. https://www.hebirobotics.com/robot-kits. See also Robotics Guide entry: https://robotsguide.com/robots/daisy

### Physical
- Mass: 18 kg
- Body dimensions: approximately 1000 mm × 1000 mm footprint, 500 mm height
- DOF/leg: 3 (hip abduction/adduction, hip flexion/extension, knee flexion/extension)
- Total actuators: 18 (12× X8-9 actuators + 6× X8-16 actuators; X8 designates 80 mm diameter, number denotes torque class)
- Actuator type: HEBI Robotics X-Series smart brushless DC actuator — integrates brushless motor, planetary gearhead, series-elastic spring element, dual encoders (motor + output), IMU (3-axis accelerometer + gyroscope), and full control electronics per module

### Electronics & Communication
- Architecture: Fully distributed per-joint electronics — each X-Series actuator is a self-contained smart module with integrated MCU running ChibiOS for real-time motor control; each module handles its own position/velocity/torque control loop; an Intel NUC PC in the chassis runs user application code and sends setpoints; modules are daisy-chained via 100/100 Mbps Ethernet over plastic optical fibre (POF)
- Interface: 10/100 Mbps Ethernet (POF) daisy-chain; UDP-based HEBI protocol at ~100 Hz command and feedback rate; each actuator exposes position, velocity, torque (via spring deflection), IMU data, winding temperature, current, and voltage feedback per cycle

### Locomotion & Control
- Gaits demonstrated: Walking over rough terrain, spider-like gait adaptation; maximum speed ~1 km/h
- Terrain: Unstructured rough terrain; exhibited at science museum; used in research for load-carrying optimisation and gait adaptation
- Control approach: Per-joint closed-loop control with simultaneous position, velocity, and torque (impedance) control modes available; user sets gains via API; demo code and full APIs in C++, ROS, Python, and MATLAB provided; series-elastic actuation enables torque sensing and compliant control; researchers have applied joint-torque optimisation and proprioceptive terrain adaptation

### Key gap / limitation
The X-Series actuators are now discontinued (replaced by T-Series and R-Series), creating a long-term support concern for Daisy-based research platforms. The Ethernet-based communication (100 Hz loop rate) introduces latency compared to direct PWM or CAN bus solutions; real-time performance depends on OS scheduling. The platform is expensive (commercial research kit pricing) and relatively heavy at 18 kg, making it impractical for compact or low-cost hexapod designs. Gain tuning documentation acknowledges that finding good gains for multi-DOF systems is non-trivial and application-dependent, with no automated identification procedure. The modular approach trades integration density for cost and mass.

### Suggested BibTeX entry
```bibtex
@misc{hebi2017daisy,
  author       = {{HEBI Robotics}},
  title        = {{Daisy 18-DoF Hexapod Kit}},
  year         = {2017},
  howpublished = {Product / robot kit, \url{https://www.hebirobotics.com/robot-kits}}
}
```
