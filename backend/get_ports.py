import serial.tools.list_ports
with open('ports_info.txt', 'w') as f:
    for p in serial.tools.list_ports.comports():
        f.write(f"{p.device} | {p.description} | {p.hwid}\n")
