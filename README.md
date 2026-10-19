# Quantum-Demonstrator-Lite
A Plug and play Quantum Algorythm for Students. Integrates into SpinDrops, a software for visualising up to three Qubits, with fully customisable Quantum Gates.


![Title Pic of setup](pics/title_pic.JPG)
*Picture of the Setup used at the Max Planck Institute of Quantum Optics*


The Quantum Demonstrator Lite can be used to demonstrate algorithms up to three Qubits over seven positions, and these can be viewed in Detail with the Spin Drops Software, available at https://spindrops.org/2.5.0-beta1/download.html *(We recommend going with the Beta, as it has the updated visualisation)*


The Quantum Demontrator Lite utilises 21 RC522 readers to maximise flexibility with the Quantum gates, allowing you to create your own custom gates. These are being controlled by a Raspberry Pi Pico2 Microcontroller, which in turn communicates with the PC over USB. 

It was designed to be somewhat affordable to institutions and Schools, with a price around 400€ depending of the suppliers you choose, and the means of assembly.

# Getting Started
For anybody wanting to build the Demonstrator, you should have a few prerequisite Tools:
| Tool | |
| --- | --- |
| 3D Printer | Ideally one with a Printbed bigger than 300x250, but 250x250 can also accomodate all parts. The ability to Print Mulit Colour is also very Helpful for printing the Gates|
| Soldering Iron | A fine tipped Soldering Station/Iron is necesary, should you decide to assemble the PCB yourself, Solder flux, tweezers, tin snips and more standard Soldering tools are required|
| Hex Bits | A standard Metric Set of Hex bits |

*Note: Should you decide to assemble the PCB yourself, be aware the SMD components are not the easiest to work with. A revamped version is a WIP which will drasitcally reduce the amount of components needed*

## Electronics
|[`Electronics/`](Electronics/README.md) contains the PCB Schematic and Board design. The PCB was designed in KiCad.
Parts needed for the PCB can be found via the Schematics, the BOM or here.

### Main PCB
The Main PCB contains the Raspberry Pi Pico and all the power conversion needed to power the NFC readers, the LEDs and the Pi Pico itself.

| ID | Designator | Value/Component | Footprint | Qty | Source | Cost |
|:---:|:---|:---|:---|:---:|:---|:---:|
| 1 | A2 | Rapberry Pi Pico 2 | Pico SMD | 1 | [Conrad](https://www.conrad.de/de/p/raspberry-pi-pico-2-mikrocontroller-pico-2-3305690.html) | 5€ |
| 2 | Cbst1, Cbst2 | 100nF | 0805 SMD | 2 | [Supplier](URL) | |
| 3 | Cin1, Cin2  Cin3, Cin4 | 10µF | 0805 SMD | 4 | [Supplier](URL) | |
| 4 | Cout1, Cout2, Cout3 | 22µF | 0603 SMD | 3 | [Supplier](URL) | |
| 5 | Cout4 | 47µF | 1206 SMD | 1 | [Supplier](URL) | |
| 6 | F1 | 5A Fuse | 1206 SMD | 1 | [Supplier](URL) | |
| 7 | J1 | USB-C 16Pin | USB-C 16P | 1 | [Supplier](URL) | |
| 8 | J4 | Barrel Jack | Barrel Jack | 1 | [Digikey](https://www.digikey.de/de/products/detail/w%C3%BCrth-elektronik/694106301002/5047522?s=N4IgTCBcDaIGwE4AsBGADHAzG9aIF0BfIA) | 1€ |
| 9 | L1 | 2.2µH | ANR6045 SMD | 1 | [Supplier](URL) | |
| 10 | L2 | 4.7µH | 1008 SMD | 1 | [Supplier](URL) | |
| 11 | PCBconn1.1–3.2 | Molex Miligrid 4x2 | 08x04 THT | 4 | [Digikey](https://www.digikey.de/de/products/detail/molex/0878310820/679677) | 7,50€ |
| 12 | PCBconn1.1–3.2 | Molex Miligrid 4x2 | 08x04 THT | 2 | [Digikey](https://www.digikey.de/de/products/detail/molex/0878330831/2405183) | 5€ |
| 13 | R1, R2 | 5.1kΩ | 0805 SMD | 1 | [Supplier](URL) | |
| 14 | R3 | 160 Ω | 0805 SMD | 1 | [Supplier](URL) | |
| 15 | R6 | 100kΩ | 0805 SMD | 1 | [Supplier](URL) | |
| 16 | Rfbb1, Rfbb2 | 10kΩ | 0805 SMD | 2 | [Supplier](URL) | |
| 17 | Rfbt1 | 33.2kΩ | 0805 SMD | 1 | [Supplier](URL) | |
| 18 | Rfbt2 | 56.2kΩ | 0805 SMD | 1 | [Supplier](URL) | |
| 19 | SW2 | Switch with LED | R1966 SW SMD | 1 | [Digikey](https://www.digikey.de/de/products/detail/e-switch/R1966ABLKBLKESRED/251346?s=N4IgTCBcDaIEoEYCcA2FBBAQgGQNI9wFEBlOQgERAF0BfIA) | 2,50€ |
| 20 | U1 | TPS563200DDCR | SOT-23-6 SMD | 1 | [Supplier](URL) | |
| 21 | U2 | TPS561201DDCR | SOT-23-6 SMD | 1 | [Supplier](URL) | |

For a complete PCB assembbly service, you can expect to pay ~85€ 

Parts 1, 8, 11, 12 and 19 will have to be hand soldered. Numbers 8, 9 and 12 are Normal THT components, 19 has to be wired and then soldered.
The Raspberry Pi Pico2 has an Unusual way of soldering it to the PCB, due to the assumption one doesn't have a hotplate available.

| Top Side | Bottom Side |
|:--:|:--:|
|![PCB Top](pics/elektronik_1.png)|![PCB Bottom](pics/elektronik_2.png)
||*Marked by the red Arrow are two through Holes, **these must be kept unfilled**, double check this when ordering the PCB* 

First solder down two of the SMD Pads of the Pi Pico, then turn the board around and fill the Marked through holes with solder, make sure to keep it warm for a bit, and probe the PCB for connection between the USB and the data pins on the Pi Pico.

### Connecting PCBs
The Quantum Demonstrator uses three almost identical PCBs to connect the individual NFC Readers to the Main PCB. These Connecting PCBs also mount the LEDs for the illumination. While all of the Connecting PCBs are the same, the Placement of the connectors is different for one of the three boards. 
These connectors are labeled with A.1, A.2 and B.1, B.2. This is neccessary due to cabeling and space saving.

**Two Boards must be configured with the A.1 and A.2 ports soldered and one Board with the B.1 and B.2 ports**
![Conn PCB](pics/elektronik_3.png)


For all three Connection PCB, you will need:
| ID | Designator | Value/Component | Footprint | Qty | Source | Cost |
|:---:|:---|:---|:---|:---:|:---|:---:|
| 1 | LEDStrip1 5m | WS2815 12V LED Strip | 500x10mm | 1 | [Amazon](https://www.amazon.de/-/en/SEZO-Upgraded-Individually-Addressable-Non-Waterproof/dp/B0DNHVZDY6?) | 25€ |
| 2 | J2-J9 | Conn\_01x08\_Socket | THT | 30 | [Conrad](https://www.conrad.de/de/p/mpe-garry-stiftleiste-standard-anzahl-reihen-1-polzahl-je-reihe-8-087-1-008-0-s-xs0-1260-1-st-734023.html) | 5,50€ |
| 3 | PCBconnA.1 - A.2 | Conn\_02x04\_Counter\_Clockwise | THT | 6 | [Digikey](https://www.digikey.de/de/products/detail/molex/0878330831/2405183) | 13€ |


### Miscelaneous Parts
*Important Note for the NFC readers: **These must be the JoyIT readers, as the pinout is not compatible between different vendors.** The ones we specify have to have straight Through hole connectors, you can desolder the included conneectors or order via JoyIT directly and ask to have these connectors omitted, such that you can solder your own.*

| ID | Designator | Value/Component | Qty | Source | Cost |
|:---:|:---|:---|:---:|:---|:---:|
| 1 | NFC Reader | JoyIT RC522 | 21 | [Conrad](https://www.conrad.de/de/p/joy-it-sbc-rfid-rc522-rfid-set-1-st-1503746.html) | 112€ |
| 2 | Cables 218509-1083 | Molex Milligrid 02x08 locking | 6 | [Mouser](https://www.mouser.de/en/ProductDetail/Molex/218509-1083?qs=A6eO%252BMLsxmQCsrsfTUrgcg%3D%3D) | 25,15€ |
| 3 | NFC Tags | 38 mm - NTAG 213 - 180 Byte | 50 | [NFC-Tag-Shop](https://www.nfc-tag-shop.de/en/NFC-Sticker-PET-38-mm-NTAG-213-180-Byte-white/68261) | 29,50€ |


## Mechanical Construction
The Case for the Quantum Demonstrator is Mostly 3D Printed, with two extra Aluminium Extrusions for stability. 

Rccommended Print settings:
| | | | | | |
|:---|:---:|:---|:---:|:---|:---:|
| Material: | PLA or PETG | Print Bed: | Satin or Textured | Infill: | 10-15% Gyroid|
| Nozzle Size: | 0.4mm | Layer height: | 0.15mm | Supports: | Only on bed |

### Bill of Materials
| Item | Quantity | Description | Suplier | Costs |
|:---:|:---:|:---|:---|:---:|
| 1 | 1 | PCB Main | | 100€ |
| 2 | 3 | Conn PCB | | 43€ |
| 3 | 1 | Switch | | 2,50€ |
| 4 | 2 | 594 mm 2020 Profile| [Motedis](https://www.motedis.com/de/Aluprofil-20x20-B-Typ-Nut-6) | 9€ |
| 5 | 1 | 🔴 Front Centre | | |
| 6 | 1 | 🔴 Middle Centre | | |
| 7 | 1 | 🔴 Rear Centre | | |
| 8 | 1 | 🔴 Corner Shoulder 1 | | |
| 9 | 1 | 🔴 Middle Shoulder 1 | | |
| 10 | 2 | 🔴 Corner Shoulder 2 | | |
| 11 | 1 | 🔴 Corner Shoulder 3 | | |
| 12 | 1 | 🔴 Middle Shoulder 2 | | |
| 13 | 3 | 🔴 Feet | | |
| 14 | 1 | 🔴 Lid Part 1/3 | | |
| 15 | 1 | 🔴 Lid Part 3/1 | | |
| 16 | 1 | 🔴 Lid Part 2 | | |
| 17 | 31 | Hex screw M4x0.70 x 12 A2 | [Motedis](https://www.motedis.com/de/Zylinderschraube-mit-Innensechskant-nach-DIN-912/M4x12) | 4,17€ |
| 18 | 6 | Hex socket head cap screw M4x0.70 x 40 A2 | [Motedis](https://www.motedis.com/de/Sonderschraube-Stossverbinder-M4x40-180G-N5-I-Typ) | 1,70€ |
| 19 | 12 | Hex countersunk screw M4x0.70 x10 A2 | [Motedis](https://www.motedis.com/de/Senkschraube-mit-Innensechskant-nach-DIN-7991/M4x10) | 3,17€ |
| 20 | 2 | 🔴 Lidholder type 1 | | |
| 21 | 2 | 🔴 Lidholder type 2 | | |
| 22 | 2 | 🔴 Lidholder type 3 | | |
| 23 | 2 | PETG 3D-printing Filament | [Prusa3D]({https://www.prusa3d.com/product/prusament-petg-prusa-galaxy-black-1kg-nfc) | 58€ |
| 24 | 39 | Heatset Insert M4| [CNC Kitchen](https://cnckitchen.store/products/heat-set-insert-m4-x-4-short-version-100-pieces)|9,40€|
| 25 | xx | Heatset Insert M2|||
| 26 | xx | T-Nut6-M4  Bosch Rexroth compatible|||

*BOM of Assembly 1, List of Parts to 3D print marked in (🔴)*

*Todo: Link Parts in here to parts in Project*
![Positions of Heatset inserts](/pics/prusaxl_print.png)
On the Prusa XL this would need 4-5 Printbeds


## Assembly of the Case

### Heatset Inserts
In preperation for assembly, insert the threaded Heatset Inserts into the pre made holes.
For this set your soldering iron to aroun 250°C and slowly but firmly melt and press the insert into the hole. Try to keep it as level as possible to the Surface. The Following pcitures show where to position the Inserts.
| Top Side | Bottom Side |
|:--:|:--:|
|![Positions of Heatset inserts](/pics/heatset_inserts_marked.png)|![Positions of Heatset inserts](/pics/heatset_inserts_marked_2.png)

### Connection to the Aluminium Extrusion
![Positions of Screws](/pics/cad_2.png)
There are multiple screwholes from the outside accessing the Aluminium extrusion. Insert the Matching screw, at a T-Nut onto it, and slide it onto the Aluminium Extrusion. 
Start with the Shoulder Sections, then do the middle section, then the Feet to tie it all to gether. Only put the lid on right at the end.

### Mounting of PCBs
The Connection PCBs are screwed down with three M4 Screws, while the Main PCB is screwed down with three M2 screws.
![Positions of Screws](/pics/cad_3.png)

### Installing LEDs
Glue the LED strip down on the marked region. Make sure the Pinout is correct, adn solder it to the given Pads.
To aid in diffusion a Thin plastic sheet is glued to the back of the Lid pieced to coder the Lighting slits (A piece of paper also works).

## Software
The Quantum Demonstrator requires some Embedded and some PC side software. 
### Prerequisites
| Software | |
| --- | --- |
| PlatformIO | A means to flash the C++ onto the RaspberryPi Pico via USB e.g. PlatformIO in VSCodium|
| Python 3.14| or newer. Needed for the PC Side software
| Tkinter 3.14 | or newer. Needed for the GUI on the PC side|

### Embedded Software
Flash the C++ Program [`main.cpp`](Embedded_Software/src/main.cpp) onto the Raspberry Pi Pico 2 via USB. 

### PC Side Software 
Download the [`PC_side_Software/`](/PC_side_Software/README.md) folder and run 


    python main.py          

Quick check without hardware or GUI:

    python selftest.py

**For a more in depth explaination:** [`/PC_side_Software/README.md/`](/PC_side_Software/README.md)

## Constructing the Quantum Gates
Download the desired Gates from [`/CAD files/Quantum Gates/`](/CAD%20files/Quantum%20Gates/) and 3D print them. Then glue An NFC Tag into each Indent (on single Qubit gates only one, on Mulit Qubit gates two or even three)


# Using the Quantum Demonstrator (Work in Progress)
Connect the Demonstrator to 12V power and USB, and Turn it on
Start python main.py and select the USB device in the dropdown Menu, and check if you can see Gates appear when you place them on the readers.
![Software view V1](/pics/software1.png)
"The Autowrite Json" automatically writes the JSON ever time an update is registered. This mean you can cuntinously import these files into spindrops.
Now Start spindrops and import the newest generated Json File.
Congratulations! You now have a functioning Quantum Demonstrator.

# Enrolling New Gates into the Database (Heavy Work in Progress)
Run
    python enroll.py --port /dev/ttyACM0
and then follow the instructions. The Names are only Important if you want to designate your own gates

| Real World Gate | Database Shortname to use|
| --- | --- |
| Hadamard | **H**|
| Not | **X** |
| Phase | **Phase([deg])**|
| | | 
