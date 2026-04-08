# New Hexapod Platforms — Literature Review Candidates

Platforms not already covered by RHex, AMOS-II, LAURON, PhantomX, or HEBI Daisy.
Each entry has a citable source confirmed via web search (April 2026).

---

## HECTOR (Hexapod Robot)

**Origin:** University of Bielefeld (CITEC / Computational Neuroscience group), Germany  
**Year:** 2012 (first platform paper); 2014 (compliant-drive paper)  
**Relevance:** Demonstrates a fully distributed, per-joint smart-drive architecture — each of the 18 joints has its own embedded processor, sensor, and elastic element communicating over a custom RS-485 bus (BioFlexBus) — directly paralleling the architecture goal of this project.  
**Citation:**  
- Schneider, A., Paskarbeit, J., Schaeffersmann, M., and Schmitz, J. "HECTOR, a New Hexapod Robot Platform with Increased Mobility — Control Approach, Design and Communication." In *Advances in Autonomous Mini Robots*, U. Rückert et al. (eds.), Springer, Berlin, 2012, pp. 249–264. DOI: 10.1007/978-3-642-27482-4_24  
- Schneider, A., Paskarbeit, J., Schilling, M., and Schmitz, J. "HECTOR, A Bio-Inspired and Compliant Hexapod Robot." In *Biomimetic and Biohybrid Systems — Living Machines 2014*, Lecture Notes in Computer Science, vol. 8608, Springer, Cham, 2014. DOI: 10.1007/978-3-319-09435-9_51

### Physical
- DOF/leg: 3 (hip swing, hip lift, knee)
- Total actuators: 18
- Actuator type: Custom serial elastic actuators (brushless DC + elastomer coupling + integrated encoder/torque sensing); body size approximately stick-insect scale with long legs

### Electronics & Communication
- Architecture: Fully distributed — each joint drive is self-contained with its own microcontroller, position sensor, and elastic element. A BioFlex bus master for each body segment (pair of legs) aggregates the two legs of that segment and connects to the central controller.
- Interface: Custom RS-485 hardware layer (BioFlexBus); wiring in each leg reduced to a single bus cable plus power rail.

### Control approach
Walknet-based decentralised neural control (per-leg controllers coordinating via inter-leg signals) drives position commands to the per-joint drives. Each joint drive closes a local position loop independently. The elastic element provides passive compliance and enables torque estimation from deformation, supporting load-sensitive reflex behaviours.

### Key gap / limitation
The hardware is bespoke and expensive (custom SEA drives, custom bus). HECTOR demonstrates what full per-joint distributed control looks like in a research hexapod, but the cost and complexity make it inaccessible for low-budget platforms. This motivates the present work: achieving per-joint closed-loop control using commodity micro servos and a compact I2C driver board.

### Suggested BibTeX entry
```bibtex
@inproceedings{schneider2012hector,
  author    = {Schneider, Axel and Paskarbeit, Jan and Schaeffersmann, Martin and Schmitz, Josef},
  title     = {{HECTOR}, a New Hexapod Robot Platform with Increased Mobility ---
               Control Approach, Design and Communication},
  booktitle = {Advances in Autonomous Mini Robots},
  editor    = {R{\"u}ckert, Ulrich and Joaquin, Sitte and Felix, Werner},
  publisher = {Springer},
  address   = {Berlin, Heidelberg},
  year      = {2012},
  pages     = {249--264},
  doi       = {10.1007/978-3-642-27482-4_24},
}

@inproceedings{schneider2014hector,
  author    = {Schneider, Axel and Paskarbeit, Jan and Schilling, Malte and Schmitz, Josef},
  title     = {{HECTOR}, A Bio-Inspired and Compliant Hexapod Robot},
  booktitle = {Biomimetic and Biohybrid Systems --- Living Machines 2014},
  series    = {Lecture Notes in Computer Science},
  volume    = {8608},
  publisher = {Springer},
  address   = {Cham},
  year      = {2014},
  doi       = {10.1007/978-3-319-09435-9_51},
}
```

---

## CTU-Prague Hexapod (Faigl/Čížek platform)

**Origin:** Czech Technical University in Prague (CTU), Faculty of Electrical Engineering, Computational Robotics group  
**Year:** 2019  
**Relevance:** Shows the acute practical limitations of a daisy-chained Dynamixel bus on an 18-servo hexapod — transport delay accumulates as servos are polled in sequence, forcing the control architecture to use a leg dynamic model to compensate; directly illustrates the motivation for a lower-latency per-leg communication scheme.  
**Citation:** Faigl, J. and Čížek, P. "Adaptive Locomotion Control of Hexapod Walking Robot for Traversing Rough Terrains with Position Feedback Only." *Robotics and Autonomous Systems*, vol. 116, pp. 136–147, 2019. DOI: 10.1016/j.robot.2019.03.008

### Physical
- DOF/leg: 3
- Total actuators: 18
- Actuator type: Dynamixel AX-12A smart servos (programmable position/torque feedback via half-duplex serial bus)

### Electronics & Communication
- Architecture: Single-board centralized computer (Odroid XU-4) connected to all 18 Dynamixel servos in a single daisy-chain TTL serial bus. No per-leg sub-controllers. All servos on one logical bus; polling is sequential.
- Interface: Dynamixel TTL half-duplex serial (UART); each read incurs a transport delay proportional to chain length.

### Control approach
Minimalistic adaptive locomotion using only servo position feedback (no additional ground-contact sensors). The controller uses a dynamic model of the robot leg combined with a model of the internal servo controller (Dynamixel's fixed proportional-position control law) to compensate for communication delay and to infer foot–ground contact from unexpected position errors. The approach explicitly models the servo's own fixed-gain internal loop as part of the plant.

### Key gap / limitation
The Dynamixel AX-12A has programmable (but still internal) position PID — better than a standard hobby servo, but still not directly tunable per-joint in real time. The single daisy-chain architecture creates unbounded polling latency as robot size grows. The paper's model-based compensation approach is a workaround for the inability to close the loop externally; the present work removes that need by externalising control entirely.

### Suggested BibTeX entry
```bibtex
@article{faigl2019adaptive,
  author    = {Faigl, Jan and {\v{C}}{\'{i}}{\v{z}}ek, Petr},
  title     = {Adaptive Locomotion Control of Hexapod Walking Robot
               for Traversing Rough Terrains with Position Feedback Only},
  journal   = {Robotics and Autonomous Systems},
  year      = {2019},
  volume    = {116},
  pages     = {136--147},
  doi       = {10.1016/j.robot.2019.03.008},
}
```

---

## MiniRHex

**Origin:** Robomechanics Lab, Carnegie Mellon University, Pittsburgh, USA  
**Year:** 2018  
**Relevance:** A small, low-cost open-source hexapod explicitly designed for research and education; uses one Dynamixel XL-320 per leg (6 actuators total) on a daisy-chain serial bus from an Arduino MKR board — a concrete example of the wiring and cost constraints that apply at small scale, and of the trade-offs made when scaling down to a single actuator per leg.  
**Citation:** Barragan, M., Flowers, N., and Johnson, A. M. "MiniRHex: A Small, Open-source, Fully Programmable Walking Hexapod." In *Robotics: Science and Systems Workshop on Design and Control of Small Legged Robots*, Pittsburgh, PA, June 2018. URL: https://www.andrew.cmu.edu/user/amj1/papers/RSS2018ws_MiniRHex.pdf

### Physical
- DOF/leg: 1 (single rotating compliant leg, C-leg design inherited from RHex)
- Total actuators: 6 (one Dynamixel XL-320 per leg)
- Actuator type: Dynamixel XL-320 (programmable smart servo, TTL serial, integrated position feedback)

### Electronics & Communication
- Architecture: Single central Arduino MKR WiFi 1010 with a Dynamixel shield; all six servos daisy-chained on one serial bus. 3D-printed chassis; laser-cut frame.
- Interface: Dynamixel TTL serial (half-duplex UART) daisy chain; unique IDs assigned per servo.

### Control approach
Open-loop gait timing: leg position commands sent as periodic position targets; no external feedback loop beyond the Dynamixel's internal position control. Software package supports gait parameter sweeps for research/education. The Dynamixel's internal PID is used as-is; gains are not re-tuned per leg.

### Key gap / limitation
With only one DOF per leg, per-joint tuning is not a concern here — but the platform illustrates the minimum-viable electronics architecture for a small research hexapod and highlights that even a single daisy-chain bus per robot is a recognised wiring simplification over 18 individual PWM cables. The internal PID is not externally accessible, which is precisely the limitation this project addresses for a higher-DOF platform.

### Suggested BibTeX entry
```bibtex
@inproceedings{barragan2018minirhex,
  author    = {Barragan, M. and Flowers, N. and Johnson, Aaron M.},
  title     = {{MiniRHex}: A Small, Open-source, Fully Programmable Walking Hexapod},
  booktitle = {Robotics: Science and Systems Workshop on Design and Control
               of Small Legged Robots},
  address   = {Pittsburgh, PA},
  month     = jun,
  year      = {2018},
  url       = {https://www.andrew.cmu.edu/user/amj1/papers/RSS2018ws_MiniRHex.pdf},
}
```

---

## Titan 6 (CMU Modular Hexapod)

**Origin:** Biorobotics Laboratory, Carnegie Mellon University / HEBI Robotics, Pittsburgh, USA  
**Year:** 2019  
**Relevance:** A large field-deployable modular hexapod where each joint is an independent self-contained smart actuator (HEBI X-series module) with its own embedded control, Ethernet communication, and per-joint PID — the highest-fidelity example of distributed per-joint control in a hexapod, providing a research-grade baseline for what the present project aims to achieve in miniature.  
**Citation:** Martone, M. "Design and Control of a Large Modular Robot Hexapod." Master's Thesis, Carnegie Mellon University Robotics Institute, Technical Report CMU-RI-TR-19-79, November 2019. URL: https://www.ri.cmu.edu/publications/design-and-control-of-a-large-modular-robot-hexapod/

### Physical
- DOF/leg: 3
- Total actuators: 18
- Actuator type: HEBI X-series modular smart actuators (brushless DC + harmonic drive + integrated IMU, encoders, temperature, and embedded position/torque/velocity PID); each module is field-replaceable

### Electronics & Communication
- Architecture: Fully distributed — each joint module runs its own embedded control loop independently. Modules communicate over 10/100 Mbps Ethernet (UDP). A laptop or companion computer sends high-level trajectory commands; each module closes its own loop locally.
- Interface: Standard Ethernet (100BASE-TX); HEBI API over UDP. No central servo controller board; cabling is one Ethernet cable plus power per joint, routed through the leg structure.

### Control approach
Per-joint PID with tunable gains (accessible via HEBI API), compliance control, and gravity compensation. The thesis explores how leg compliance improves stability on uneven terrain. The controller leverages the compliance of the series-elastic elements within each X-series module to absorb contact impulses.

### Key gap / limitation
Cost and scale preclude direct adoption in a small hexapod: each HEBI X-series module costs several hundred dollars, and the Ethernet-per-joint cabling is impractical at palm size. Titan 6 defines the goal state of per-joint distributed control; the present work pursues a functionally equivalent architecture at micro-servo scale and cost.

### Suggested BibTeX entry
```bibtex
@mastersthesis{martone2019titan6,
  author  = {Martone, Matthew},
  title   = {Design and Control of a Large Modular Robot Hexapod},
  school  = {Carnegie Mellon University, Robotics Institute},
  year    = {2019},
  month   = nov,
  type    = {Master's Thesis},
  note    = {CMU-RI-TR-19-79},
  url     = {https://www.ri.cmu.edu/publications/design-and-control-of-a-large-modular-robot-hexapod/},
}
```

---

## Notes on platforms considered but excluded

- **Lynxmotion Phoenix / SSC-32U**: Well-known hobby platform (18 Hitec servos, centralised SSC-32 PWM controller) but no peer-reviewed paper found — only product documentation and community forum posts. Useful as a footnote illustration of the centralised-PWM architecture, but not citable at the required level.
- **Vorpal Hexapod**: Open-source 12-servo educational hexapod (MG90S, Arduino, centralised control); only maker-community sources found (Kickstarter, Hackaday). No citable academic paper.
- **MX-Phoenix**: DIY Dynamixel hexapod (MX-64/MX-106, Teensy 3.6); only blog posts and GitHub. No citable paper.
- **OpenHexapod**: RobotShop community project circa 2011; no peer-reviewed citation.
- **Hexy (ArcBotics)**: Open-source 19-servo Arduino hexapod kit; only product pages and community write-ups found.
