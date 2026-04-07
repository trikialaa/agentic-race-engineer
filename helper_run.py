import os
import subprocess
import time


def main():
    helper_path = os.path.join("native", "wheel-helper", "bin", "WheelHelper.exe")
    proc = subprocess.Popen(
        [helper_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(3)
    proc.terminate()
    out, err = proc.communicate()
    print("STDOUT:")
    print(out)
    print("STDERR:")
    print(err)


if __name__ == "__main__":
    main()
