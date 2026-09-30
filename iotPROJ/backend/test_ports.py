import serial
import serial.tools.list_ports

def main():
    ports = serial.tools.list_ports.comports()
    results = []
    for p in ports:
        res = f"Testing port {p.device} ({p.description})\n"
        try:
            with serial.Serial(p.device, 115200, timeout=2) as s:
                data = s.readline()
                res += f"  Success! Read: {data}\n"
        except Exception as e:
            res += f"  Failed: {e}\n"
        results.append(res)
        
    with open('ports_result.txt', 'w') as f:
        f.writelines(results)

if __name__ == '__main__':
    main()
