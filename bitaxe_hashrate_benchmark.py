import requests
import time
import json
import signal
import sys
import argparse
import statistics
from datetime import datetime
START_TIME = datetime.now().strftime("%Y-%m-%d_%H")


if 'START_TIME' not in globals():
    START_TIME = datetime.now().strftime("%Y-%m-%d_%H")

# Enable ansi escape characters in terminal - colors were not working in Windows terminal
import os
try:
    import colorama
    colorama.init()
except ImportError:
    # Fallback for environments where colorama isn't available
    if os.name == "nt":
        os.system("")  # rudimentary ANSI enable on Windows

# Compute timestamp for file suffix
timestamp = time.strftime("%Y%m%d-%H%M%S")

# ANSI Color Codes
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"

# This formatter allows for multi-line descriptions in help messages and adds default values
class RawTextAndDefaultsHelpFormatter(argparse.RawTextHelpFormatter):
    def _get_help_string(self, action):
        help_text = super()._get_help_string(action)
        if action.default is not argparse.SUPPRESS:
            # Append default value to help text if available
            defaulting_nargs = [argparse.OPTIONAL, argparse.ZERO_OR_MORE]
            if action.option_strings or action.nargs in defaulting_nargs:
                if "\n" in help_text:
                    help_text += f"\n(default: {action.default})"
                else:
                    help_text += f" (default: {action.default})"
        return help_text

# Modify the parse_arguments function
def parse_arguments():
    parser = argparse.ArgumentParser(
        description=
        f"{GREEN}Bitaxe Hashrate Benchmark Tool v1.0{RESET}\n"
        "This script allows you to either benchmark your Bitaxe miner across various "
        "voltage and frequency settings, or apply specific settings directly.\n",
        epilog=
        f"{YELLOW}Examples:{RESET}\n"
        f"  {YELLOW}1. Run a full benchmark (starting at 1150mV, 500MHz):{RESET}\n"
        f"     {GREEN}python bitaxe_hasrate_benchmark.py 192.168.1.136 -v 1150 -f 500{RESET}\n\n"
        f"  {YELLOW}2. Apply specific settings (1150mV, 780MHz) and exit:{RESET}\n"
        f"     {GREEN}python bitaxe_hasrate_benchmark.py 192.168.1.136 --set-values -v 1150 -f 780{RESET}\n\n"
        f"  {YELLOW}3. Get help (this message):{RESET}\n"
        f"     {GREEN}python bitaxe_hasrate_benchmark.py --help{RESET}",
        formatter_class=RawTextAndDefaultsHelpFormatter # <--- USE THE CUSTOM FORMATTER
    )

    # Positional Argument
    parser.add_argument(
        'bitaxe_ip',
        nargs='?', # Makes it optional if --help is used alone, but required otherwise
        help=f"{YELLOW}IP address of your Bitaxe miner (e.g., 192.168.2.26){RESET}\n"
             "  This is required for both benchmarking and setting values."
    )

    # Optional Arguments
    parser.add_argument(
        '-v', '--voltage',
        type=int,
        default=1150, # Default value for benchmark start or target setting
        help=f"{YELLOW}Core voltage in mV.{RESET}\n"
             "  For benchmark mode: The starting voltage for testing.\n"
             "  For --set-values mode: The exact voltage to apply."
    )
    parser.add_argument(
        '-f', '--frequency',
        type=int,
        default=500, # Default value for benchmark start or target setting
        help=f"{YELLOW}Core frequency in MHz.{RESET}\n"
             "  For benchmark mode: The starting frequency for testing.\n"
             "  For --set-values mode: The exact frequency to apply."
    )

    # New argument for setting values only
    parser.add_argument(
        '-s', '--set-values',
        action='store_true',
        help=f"{YELLOW}Set values only; do not run benchmark.{RESET}\n"
             "  If this flag is present, the script will apply the voltage (-v) and\n"
             "  frequency (-f) settings to the Bitaxe and then exit."
    )

    parser.add_argument(
        '--max-temp',
        type=int,
        default=66,
        help=f"{YELLOW}Maximum chip temperature in °C (default: 66).{RESET}\n"
             "  The benchmark will stop if this temperature is exceeded."
    )

    # If no arguments are provided, print help and exit
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    return parser.parse_args()

# Replace the configuration section
args = parse_arguments()
bitaxe_ip = f"http://{args.bitaxe_ip}"
initial_voltage = args.voltage
initial_frequency = args.frequency

# Configuration
voltage_increment = 15
frequency_increment = 20
sleep_time = 90               # Wait 90 seconds before starting the benchmark
benchmark_time = 600          # 10 minutes benchmark time
sample_interval = 15          # 15 seconds sample interval
max_temp = args.max_temp      # Will stop if temperature reaches or exceeds this value
max_allowed_voltage = 1400    # Maximum allowed core voltage
max_allowed_frequency = 1200  # Maximum allowed core frequency
max_vr_temp = 86              # Maximum allowed voltage regulator temperature
min_input_voltage = 4800      # Minimum allowed input voltage
max_input_voltage = 5500      # Maximum allowed input voltage
max_power = 30                # Max of 30W because of DC plug

# Add these variables to the global configuration section
small_core_count = None
asic_count = 1

# Add these constants to the configuration section
min_allowed_voltage = 1000  # Minimum allowed core voltage
min_allowed_frequency = 400  # Minimum allowed frequency

# Validate core voltages
if initial_voltage > max_allowed_voltage:
    raise ValueError(RED + f"Error: Initial voltage exceeds the maximum allowed value of {max_allowed_voltage}mV. Please check the input and try again." + RESET)

# Validate frequency
if initial_frequency > max_allowed_frequency:
    raise ValueError(RED + f"Error: Initial frequency exceeds the maximum allowed value of {max_allowed_frequency}Mhz. Please check the input and try again." + RESET)

# Add these validation checks after the existing ones
if initial_voltage < min_allowed_voltage:
    raise ValueError(RED + f"Error: Initial voltage is below the minimum allowed value of {min_allowed_voltage}mV." + RESET)

if initial_frequency < min_allowed_frequency:
    raise ValueError(RED + f"Error: Initial frequency is below the minimum allowed value of {min_allowed_frequency}MHz." + RESET)

if benchmark_time / sample_interval < 7:
    raise ValueError(RED + f"Error: Benchmark time is too short. Please increase the benchmark time or decrease the sample interval. At least 7 samples are required." + RESET)

# Add suffix to filename in case of manual initial voltage/frequency
file_suffix = ""
if initial_voltage != 1150:
    file_suffix = file_suffix + "_v" + str(initial_voltage)
if initial_frequency != 500:
    file_suffix = file_suffix + "_f" + str(initial_frequency)

# Refactor filename (called in multiple places)
def result_filename():
    # Extract IP from bitaxe_ip global variable and remove 'http://'
    ip_address = bitaxe_ip.replace('http://', '')
    return f"bitaxe_benchmark_results_{ip_address}_{timestamp}{file_suffix}.json"

# Results storage
results = []

# Dynamically determined default settings
default_voltage = None
default_frequency = None

# Check if we're handling an interrupt (Ctrl+C)
handling_interrupt = False

def running_stddev(N, s1, s2):
    if N > 1:
        var = (N * s2 - s1 ** 2) / (N * (N - 1))
        return max(var, 0.0) ** 0.5
    else:
        return 0.0

def fetch_default_settings():
    global default_voltage, default_frequency, small_core_count, asic_count
    
    # Try /api/system/info first - always get small_core_count from here
    try:
        response = requests.get(f"{bitaxe_ip}/api/system/info", timeout=10)
        response.raise_for_status()
        system_info = response.json()
        
        # Always get small_core_count from /system/info since it's always available there
        if "smallCoreCount" not in system_info:
            print(RED + "Error: smallCoreCount field missing from /api/system/info response." + RESET)
            print(RED + "Cannot proceed without core count information for hashrate calculations." + RESET)
            sys.exit(1)
        
        small_core_count = system_info.get("smallCoreCount")
        
        # Check if we have all the info we need from /system/info
        has_voltage = "coreVoltage" in system_info
        has_frequency = "frequency" in system_info
        has_asic_count = "asicCount" in system_info
        
        if has_voltage and has_frequency and has_asic_count:
            # We have all the info we need from /info
            default_voltage = system_info.get("coreVoltage", 1150)
            default_frequency = system_info.get("frequency", 500)
            asic_count = system_info.get("asicCount", 0)
            print(GREEN + f"Current settings determined from /api/system/info:\n"
                          f"  Core Voltage: {default_voltage}mV\n"
                          f"  Frequency: {default_frequency}MHz\n"
                          f"  ASIC Configuration: {small_core_count * asic_count} total cores" + RESET)
            return
        else:
            print(YELLOW + f"Got small_core_count ({small_core_count}) from /api/system/info, getting remaining info from /api/system/asic..." + RESET)
    except requests.exceptions.RequestException as e:
        print(RED + f"Error fetching from /api/system/info: {e}" + RESET)
        sys.exit(1)
    
    # Try /api/system/asic for updated devices
    try:
        response = requests.get(f"{bitaxe_ip}/api/system/asic", timeout=10)
        response.raise_for_status()
        asic_info = response.json()
        
        default_voltage = asic_info.get("defaultVoltage", 1150)
        default_frequency = asic_info.get("defaultFrequency", 500)
        # Keep the small_core_count we got from /system/info (don't override it)
        asic_count = asic_info.get("asicCount", 1)
        
        print(GREEN + f"Current settings determined from /api/system/asic:\n"
                      f"  Core Voltage: {default_voltage}mV\n"
                      f"  Frequency: {default_frequency}MHz\n"
                      f"  ASIC Configuration: {small_core_count * asic_count} total cores" + RESET)
        return
    except requests.exceptions.RequestException as e:
        print(RED + f"Error fetching from /api/asic: {e}" + RESET)
    
    # If both endpoints fail, exit the program
    print(RED + "Failed to fetch rest of the device information from /api/system/asic." + RESET)
    print(RED + "Cannot proceed safely without device configuration. Please check your connection and try again." + RESET)
    sys.exit(1)

# Add a global flag to track whether the system has already been reset
system_reset_done = False

def handle_sigint(signum, frame):
    global system_reset_done, handling_interrupt
    
    # If we're already handling an interrupt or have completed reset, ignore this signal
    if handling_interrupt or system_reset_done:
        return
        
    handling_interrupt = True
    print(RED + "Benchmarking interrupted by user." + RESET)
    
    try:
        if results:
            reset_to_best_setting()
            save_results()
            print(GREEN + "Bitaxe reset to best or default settings and results saved." + RESET)
        else:
            print(YELLOW + "No valid benchmarking results found. Applying predefined default settings." + RESET)
            set_system_settings(default_voltage, default_frequency)
    finally:
        system_reset_done = True
        handling_interrupt = False
        sys.exit(0)

# Register the signal handler
signal.signal(signal.SIGINT, handle_sigint)

def get_system_info():
    retries = 3
    for attempt in range(retries):
        try:
            response = requests.get(f"{bitaxe_ip}/api/system/info", timeout=10)
            response.raise_for_status()  # Raise an exception for HTTP errors
            return response.json()
        except requests.exceptions.Timeout:
            print(YELLOW + f"Timeout while fetching system info. Attempt {attempt + 1} of {retries}." + RESET)
        except requests.exceptions.ConnectionError:
            print(RED + f"Connection error while fetching system info. Attempt {attempt + 1} of {retries}." + RESET)
        except requests.exceptions.RequestException as e:
            print(RED + f"Error fetching system info: {e}" + RESET)
            break
        time.sleep(5)  # Wait before retrying
    return None

def set_system_settings(core_voltage, frequency):
    settings = {
        "coreVoltage": core_voltage,
        "frequency": frequency
    }
    try:
        response = requests.patch(f"{bitaxe_ip}/api/system", json=settings, timeout=10)
        response.raise_for_status()  # Raise an exception for HTTP errors
        print(YELLOW + f"Applying settings: Voltage = {core_voltage}mV, Frequency = {frequency}MHz" + RESET)
        time.sleep(2)
        return restart_system()
    except requests.exceptions.RequestException as e:
        print(RED + f"Error setting system settings: {e}" + RESET)
        return False

def restart_system():
    try:
        # Check if we're being called from handle_sigint
        is_interrupt = handling_interrupt
        
        # Restart here as some bitaxes get unstable with bad settings
        # If not an interrupt, wait sleep_time for system stabilization as some bitaxes are slow to ramp up
        if not is_interrupt:
            print(YELLOW + f"Applying new settings and waiting {sleep_time}s for system stabilization..." + RESET)
            response = requests.post(f"{bitaxe_ip}/api/system/restart", timeout=10)
            response.raise_for_status()  # Raise an exception for HTTP errors
            
            # Monitor system during stabilization period
            start_wait = time.time()
            while time.time() - start_wait < sleep_time:
                try:
                    info = get_system_info()
                    if info:
                        temp = info.get("temp")
                        power = info.get("power")
                        
                        if temp and temp >= max_temp:
                            print(RED + f"CRITICAL: Chip temperature {temp}°C exceeded limit {max_temp}°C during stabilization!" + RESET)
                            return False
                            
                        if power and power > max_power:
                            print(RED + f"CRITICAL: Power {power}W exceeded limit {max_power}W during stabilization!" + RESET)
                            return False
                            
                except Exception:
                    pass # Ignore transient errors during restart
                time.sleep(5)
        else:
            print(YELLOW + "Applying final settings..." + RESET)
            response = requests.post(f"{bitaxe_ip}/api/system/restart", timeout=10)
            response.raise_for_status()  # Raise an exception for HTTP errors
        
        return True
    except requests.exceptions.RequestException as e:
        print(RED + f"Error restarting the system: {e}" + RESET)
        return False

def benchmark_iteration(core_voltage, frequency):
    current_time = time.strftime("%H:%M:%S")
    print(GREEN + f"[{current_time}] Starting benchmark for Core Voltage: {core_voltage}mV, Frequency: {frequency}MHz" + RESET)
    hash_rates = []
    s1 = 0.0
    s2 = 0.0
    temperatures = []
    power_consumptions = [] 
    vr_temps = []
    fan_speeds = []
    total_samples = benchmark_time // sample_interval
    expected_hashrate = frequency * ((small_core_count * asic_count) / 1000)  # Calculate expected hashrate based on frequency
    
    for sample in range(total_samples):
        info = get_system_info()
        if info is None:
            print(YELLOW + "Skipping this iteration due to failure in fetching system info." + RESET)
            return None, None, None, None, False, None, None, None, "SYSTEM_INFO_FAILURE"
        
        temp = info.get("temp")
        vr_temp = info.get("vrTemp")  # Get VR temperature if available
        voltage = info.get("voltage")
        if temp is None:
            print(YELLOW + "Temperature data not available." + RESET)
            return None, None, None, None, False, None, None, None, "TEMPERATURE_DATA_FAILURE"
        
        if temp < 5:
            print(YELLOW + "Temperature is below 5°C. This is unexpected. Please check the system." + RESET)
            return None, None, None, None, False, None, None, None, "TEMPERATURE_BELOW_5"
        
        # Check both chip and VR temperatures
        if temp >= max_temp:
            print(RED + f"Chip temperature exceeded {max_temp}°C! Stopping current benchmark." + RESET)
            return None, None, None, None, False, None, None, None, "CHIP_TEMP_EXCEEDED"
            
        if vr_temp is not None and vr_temp >= max_vr_temp:
            print(RED + f"Voltage regulator temperature exceeded {max_vr_temp}°C! Stopping current benchmark." + RESET)
            return None, None, None, None, False, None, None, None, "VR_TEMP_EXCEEDED"

        if voltage < min_input_voltage:
            print(RED + f"Input voltage is below the minimum allowed value of {min_input_voltage}mV! Stopping current benchmark." + RESET)
            return None, None, None, None, False, None, None, None, "INPUT_VOLTAGE_BELOW_MIN"
        
        if voltage > max_input_voltage:
            print(RED + f"Input voltage is above the maximum allowed value of {max_input_voltage}mV! Stopping current benchmark." + RESET)
            return None, None, None, None, False, None, None, None, "INPUT_VOLTAGE_ABOVE_MAX"
        
        hash_rate = info.get("hashRate")
        power_consumption = info.get("power")
        fan_speed = info.get("fanspeed")    

        if hash_rate is None or power_consumption is None:
            print(YELLOW + "Hashrate or Watts data not available." + RESET)
            return None, None, None, None, False, None, None, None, "HASHRATE_POWER_DATA_FAILURE"
        
        if power_consumption > max_power:
            print(RED + f"Power consumption exceeded {max_power}W! Stopping current benchmark." + RESET)
            return None, None, None, None, False, None, None, None, "POWER_CONSUMPTION_EXCEEDED"
        
        hash_rates.append(hash_rate)
        s1 += hash_rate
        s2 += hash_rate * hash_rate
        temperatures.append(temp)
        power_consumptions.append(power_consumption)
        if vr_temp is not None and vr_temp > 0:
            vr_temps.append(vr_temp)
        if fan_speed is not None:
            fan_speeds.append(fan_speed)

        # Calculate percentage progress
        percentage_progress = ((sample + 1) / total_samples) * 100
        running_sd = running_stddev(sample + 1, s1, s2)
        status_line = (
            f"[{sample + 1:2d}/{total_samples:2d}] "
            f"{percentage_progress:5.1f}% | "
            f"CV: {core_voltage:4d}mV | "
            f"F: {frequency:4d}MHz | "
            f"H: {int(hash_rate):4d} GH/s | "
            f"SD: {running_sd:3.0f} GH/s | "
            f"IV: {int(voltage):4d}mV | "
            f"T: {int(temp):2d}°C"
        )
        if vr_temp is not None and vr_temp > 0:
            status_line += f" | VR: {int(vr_temp):2d}°C"

        # Add Power (Watts) to the status line if available
        if power_consumption is not None:
            status_line += f" | P: {int(power_consumption):2d} W"

        # Add Fan Speed to the status line if available
        if fan_speed is not None:
            status_line += f" | FAN: {int(fan_speed):2d}%"

        print(status_line + RESET)
        
        # Only sleep if it's not the last iteration
        if sample < total_samples - 1:
            time.sleep(sample_interval)
    
    if hash_rates and temperatures and power_consumptions:
        # Remove 3 highest and 3 lowest hashrates in case of outliers
        sorted_hashrates = sorted(hash_rates)
        trimmed_hashrates = sorted_hashrates[3:-3]  # Remove first 3 and last 3 elements
        average_hashrate = sum(trimmed_hashrates) / len(trimmed_hashrates)
        hashrate_stdev = statistics.stdev(trimmed_hashrates) if len(trimmed_hashrates) > 1 else 0.0
        
        # Sort and trim temperatures (remove lowest 6 readings during warmup)
        sorted_temps = sorted(temperatures)
        trimmed_temps = sorted_temps[6:]  # Remove first 6 elements only
        average_temperature = sum(trimmed_temps) / len(trimmed_temps)
        
        # Only process VR temps if we have valid readings
        average_vr_temp = None
        if vr_temps:
            sorted_vr_temps = sorted(vr_temps)
            trimmed_vr_temps = sorted_vr_temps[6:]  # Remove first 6 elements only
            average_vr_temp = sum(trimmed_vr_temps) / len(trimmed_vr_temps)
        
        average_power = sum(power_consumptions) / len(power_consumptions)

        average_fan_speed = None
        if fan_speeds:
            average_fan_speed = sum(fan_speeds) / len(fan_speeds)
            print(GREEN + f"Average Fan Speed: {average_fan_speed:.2f}%" + RESET)
        
        # Add protection against zero hashrate
        if average_hashrate > 0:
            efficiency_jth = average_power / (average_hashrate / 1_000)
        else:
            print(RED + "Warning: Zero hashrate detected, skipping efficiency calculation" + RESET)
            return None, None, None, None, False, None, None, None, "ZERO_HASHRATE"
        
        # Calculate if hashrate is within 6% of expected
        hashrate_within_tolerance = (average_hashrate >= expected_hashrate * 0.94)
        
        print(GREEN + f"Average Hashrate: {average_hashrate:.2f} GH/s (Expected: {expected_hashrate:.2f} GH/s)" + RESET)
        print(GREEN + f"Hashrate Std Dev: {hashrate_stdev:.2f} GH/s" + RESET)
        print(GREEN + f"Average Temperature: {average_temperature:.2f}°C" + RESET)
        if average_vr_temp is not None:
            print(GREEN + f"Average VR Temperature: {average_vr_temp:.2f}°C" + RESET)
        print(GREEN + f"Efficiency: {efficiency_jth:.2f} J/TH" + RESET)
        
        return average_hashrate, hashrate_stdev, average_temperature, efficiency_jth, hashrate_within_tolerance, average_vr_temp, average_power, average_fan_speed, None
    else:
        print(YELLOW + "No Hashrate or Temperature or Watts data collected." + RESET)
        return None, None, None, None, False, None, None, None, "NO_DATA_COLLECTED"

def save_results():
    try:
        # Refactored filename computation
        filename = result_filename()
        with open(filename, "w") as f:
            json.dump(results, f, indent=4)
        print(GREEN + f"Results saved to {filename}" + RESET)
        print()  # Add empty line
        
    except IOError as e:
        print(RED + f"Error saving results to file: {e}" + RESET)

def reset_to_best_setting():
    if not results:
        print(YELLOW + "No valid benchmarking results found. Applying predefined default settings." + RESET)
        set_system_settings(default_voltage, default_frequency)
    else:
        # Find best hashrate result
        best_result = sorted(results, key=lambda x: x["averageHashRate"], reverse=True)[0]
        best_voltage = best_result["coreVoltage"]
        best_frequency = best_result["frequency"]

        # Find most efficient result
        efficient_result = sorted(results, key=lambda x: x["efficiencyJTH"], reverse=False)[0]
        eff_voltage = efficient_result["coreVoltage"]
        eff_frequency = efficient_result["frequency"]

        print(GREEN + f"\n--- Benchmark Complete ---" + RESET)
        print(GREEN + f"Best Hashrate Settings: {best_voltage}mV / {best_frequency}MHz ({best_result['averageHashRate']:.2f} GH/s)" + RESET)
        print(GREEN + f"Most Efficient Settings: {eff_voltage}mV / {eff_frequency}MHz ({efficient_result['efficiencyJTH']:.2f} J/TH)" + RESET)
        
        print(YELLOW + f"\nWARNING: 'Best Hashrate' settings are often at the thermal/stability limit." + RESET)
        print(YELLOW + f"Running these settings 24/7 may reduce hardware lifespan." + RESET)
        print(YELLOW + f"Applying 'Most Efficient' settings is generally safer for long-term use." + RESET)
        
        # For now, we still default to applying the "Best Hashrate" settings as per original behavior,
        # but we've added the warning.
        print(GREEN + f"\nApplying Best Hashrate settings..." + RESET)
        set_system_settings(best_voltage, best_frequency)
    
    # restart_system() is already called inside set_system_settings, so we don't need to call it again here.

# --- Main execution logic ---
if args.set_values:
    print(GREEN + "\n--- Applying Settings Only ---" + RESET)
    print(GREEN + f"Applying Core Voltage: {initial_voltage}mV, Frequency: {initial_frequency}MHz to Bitaxe." + RESET)
    
    # Call the existing set_system_settings function
    set_system_settings(initial_voltage, initial_frequency)
    
    print(GREEN + "Settings applied. Check your Bitaxe web interface to confirm." + RESET)
    sys.exit(0) # Exit the script after applying settings

# Main benchmarking process
try:
    fetch_default_settings()
    
    # Add disclaimer
    print(RED + "\nDISCLAIMER:" + RESET)
    print("This tool will stress test your Bitaxe by running it at various voltages and frequencies.")
    print("While safeguards are in place, running hardware outside of standard parameters carries inherent risks.")
    print("Use this tool at your own risk. The author(s) are not responsible for any damage to your hardware.")
    print("\nNOTE: Ambient temperature significantly affects these results. The optimal settings found may not")
    print("work well if room temperature changes substantially. Re-run the benchmark if conditions change.\n")
    
    current_voltage = initial_voltage
    current_frequency = initial_frequency
    retry_upon_overheat = 0
    
    while current_voltage <= max_allowed_voltage and current_frequency <= max_allowed_frequency:
        if not set_system_settings(current_voltage, current_frequency):
            # If stabilization failed (e.g. overheat during boot), treat as a failed iteration
            avg_hashrate = None
            hashrate_stdev = None
            avg_temp = None
            efficiency_jth = None
            hashrate_ok = False
            avg_vr_temp = None
            avg_power = None
            avg_fan_speed = None
            error_reason = "STABILIZATION_FAILED"
        else:
            avg_hashrate, hashrate_stdev, avg_temp, efficiency_jth, hashrate_ok, avg_vr_temp, avg_power, avg_fan_speed, error_reason = benchmark_iteration(current_voltage, current_frequency)
        
        if avg_hashrate is not None and avg_temp is not None and efficiency_jth is not None:
            retry_upon_overheat = 0
            result = {
                "coreVoltage": current_voltage,
                "frequency": current_frequency,
                "averageHashRate": avg_hashrate,
                "hashrateStdDev": hashrate_stdev,
                "averageTemperature": avg_temp,
                "efficiencyJTH": efficiency_jth,
                "averagePower": avg_power,
                "errorReason": error_reason
            }
            
            # Only add VR temp if it exists
            if avg_vr_temp is not None:
                result["averageVRTemp"] = avg_vr_temp

            # Only add Fan Speed if it exists (assuming it's not None)
            if avg_fan_speed is not None:
                result["averageFanSpeed"] = avg_fan_speed
                
            results.append(result)

            if hashrate_ok:
                # If hashrate is good, try increasing frequency
                if current_frequency + frequency_increment <= max_allowed_frequency:
                    current_frequency += frequency_increment
                    print(GREEN + "Hashrate is good. Increasing frequency for next try." + RESET)
                else:
                    print(GREEN + "Reached max frequency with good results. Stopping further testing." + RESET)
                    break  # We've reached max frequency with good results
            else:
                # If hashrate is not good, go back one frequency step and increase voltage
                if current_voltage + voltage_increment <= max_allowed_voltage:
                    current_voltage += voltage_increment
                    
                    # Decrease frequency but respect the minimum limit
                    if current_frequency - frequency_increment >= min_allowed_frequency:
                        current_frequency -= frequency_increment
                    else:
                        current_frequency = min_allowed_frequency
                        
                    print(YELLOW + f"Hashrate too low compared to expected. Adjusting to {current_frequency}MHz and increasing voltage to {current_voltage}mV" + RESET)
                else:
                    print(YELLOW + "Reached max voltage without good results. Stopping further testing." + RESET)
                    break  # We've reached max voltage without good results
        else:
            # If we hit thermal limits or other issues, we've found the highest safe settings
            # In case of max Chip Temperature reached, continue loop to next voltage with decreased frequency
            # Condition added to avoid successive overheat tries and reset to high initial frequency
            
            # CRITICAL SAFETY CHECK: If we overheated at the INITIAL frequency, do NOT increase voltage.
            # Increasing voltage will only make it hotter. We should stop or decrease frequency.
            if error_reason == "CHIP_TEMP_EXCEEDED" and current_frequency == initial_frequency:
                print(RED + "Overheated at initial frequency! Cannot increase voltage safely. Stopping." + RESET)
                break

            overheat_retry_allowed = (
                error_reason == "CHIP_TEMP_EXCEEDED"
                and retry_upon_overheat < 1
                and initial_frequency <= current_frequency + frequency_increment
            )
            if overheat_retry_allowed:
                # If overheat, return to initial frequency while increasing voltage (considering max_allowed_voltage)
                retry_upon_overheat += 1
                if current_voltage + voltage_increment <= max_allowed_voltage:
                    current_frequency = initial_frequency
                    current_voltage += voltage_increment
                    print(GREEN + "Reached thermal limit for the current voltage/frequency. Switching to next voltage increment." + RESET)
                else:
                    print(GREEN + "Reached thermal limit for the current voltage/frequency. Next voltage increment out of voltage limit. Stopping further testing." + RESET)
                    break  # We've reached max voltage, can't increase voltage anymore
            else:
                print(GREEN + "Reached thermal or stability limits. Stopping further testing." + RESET)
                break  # Stop testing higher values

        save_results()

except Exception as e:
    print(RED + f"An unexpected error occurred: {e}" + RESET)
    if results:
        reset_to_best_setting()
        save_results()
    else:
        print(YELLOW + "No valid benchmarking results found. Applying predefined default settings." + RESET)
        set_system_settings(default_voltage, default_frequency)
        restart_system()
finally:
    if not system_reset_done:
        if results:
            reset_to_best_setting()
            save_results()
            print(GREEN + "Bitaxe reset to best or default settings and results saved." + RESET)
        else:
            print(YELLOW + "No valid benchmarking results found. Applying predefined default settings." + RESET)
            set_system_settings(default_voltage, default_frequency)
            restart_system()
        system_reset_done = True

    # Print results summary only if we have results
    if results:
        # Sort results by averageHashRate in descending order and get the top 5
        top_5_results = sorted(results, key=lambda x: x["averageHashRate"], reverse=True)[:5]
        top_5_efficient_results = sorted(results, key=lambda x: x["efficiencyJTH"], reverse=False)[:5]
        
        # Create a dictionary containing all results and top performers
        final_data = {
            "all_results": results,
            "top_performers": [
                {
                    "rank": i,
                    "coreVoltage": result["coreVoltage"],
                    "frequency": result["frequency"],
                    "averageHashRate": result["averageHashRate"],
                    "hashrateStdDev": result["hashrateStdDev"],
                    "averageTemperature": result["averageTemperature"],
                    "efficiencyJTH": result["efficiencyJTH"],
                    "averagePower": result["averagePower"],
                    **({"averageVRTemp": result["averageVRTemp"]} if "averageVRTemp" in result else {}),
                    **({"averageFanSpeed": result["averageFanSpeed"]} if "averageFanSpeed" in result else {})
                }
                for i, result in enumerate(top_5_results, 1)
            ],
            "most_efficient": [
                {
                    "rank": i,
                    "coreVoltage": result["coreVoltage"],
                    "frequency": result["frequency"],
                    "averageHashRate": result["averageHashRate"],
                    "hashrateStdDev": result["hashrateStdDev"],
                    "averageTemperature": result["averageTemperature"],
                    "efficiencyJTH": result["efficiencyJTH"],
                    "averagePower": result["averagePower"],
                    **({"averageVRTemp": result["averageVRTemp"]} if "averageVRTemp" in result else {}),
                    **({"averageFanSpeed": result["averageFanSpeed"]} if "averageFanSpeed" in result else {})
                }
                for i, result in enumerate(top_5_efficient_results, 1)
            ]
        }
        
        # Save the final data to JSON
        # Refactored filename computation
        filename = result_filename()
        with open(filename, "w") as f:
            json.dump(final_data, f, indent=4)
        
        print(GREEN + "Benchmarking completed." + RESET)
        if top_5_results:
            print(GREEN + "\nTop 5 Highest Hashrate Settings:" + RESET)
            for i, result in enumerate(top_5_results, 1):
                print(GREEN + f"\nRank {i}:" + RESET)
                print(GREEN + f"  Core Voltage: {result['coreVoltage']}mV" + RESET)
                print(GREEN + f"  Frequency: {result['frequency']}MHz" + RESET)
                print(GREEN + f"  Average Hashrate: {result['averageHashRate']:.2f} GH/s" + RESET)
                print(GREEN + f"  Hashrate Std Dev: {result.get('hashrateStdDev', 0.0):.2f} GH/s" + RESET)
                print(GREEN + f"  Average Temperature: {result['averageTemperature']:.2f}°C" + RESET)
                print(GREEN + f"  Efficiency: {result['efficiencyJTH']:.2f} J/TH" + RESET)
                print(GREEN + f"  Average Power: {result['averagePower']:.2f} W" + RESET)
                if "averageFanSpeed" in result:
                    print(GREEN + f"  Average Fan Speed: {result['averageFanSpeed']:.2f}%" + RESET)
                if "averageVRTemp" in result:
                    print(GREEN + f"  Average VR Temperature: {result['averageVRTemp']:.2f}°C" + RESET)
            
            print(GREEN + "\nTop 5 Most Efficient Settings:" + RESET)
            for i, result in enumerate(top_5_efficient_results, 1):
                print(GREEN + f"\nRank {i}:" + RESET)
                print(GREEN + f"  Core Voltage: {result['coreVoltage']}mV" + RESET)
                print(GREEN + f"  Frequency: {result['frequency']}MHz" + RESET)
                print(GREEN + f"  Average Hashrate: {result['averageHashRate']:.2f} GH/s" + RESET)
                print(GREEN + f"  Hashrate Std Dev: {result.get('hashrateStdDev', 0.0):.2f} GH/s" + RESET)
                print(GREEN + f"  Average Temperature: {result['averageTemperature']:.2f}°C" + RESET)
                print(GREEN + f"  Efficiency: {result['efficiencyJTH']:.2f} J/TH" + RESET)
                print(GREEN + f"  Average Power: {result['averagePower']:.2f} W" + RESET)
                if "averageFanSpeed" in result:
                    print(GREEN + f"  Average Fan Speed: {result['averageFanSpeed']:.2f}%" + RESET)
                if "averageVRTemp" in result:
                    print(GREEN + f"  Average VR Temperature: {result['averageVRTemp']:.2f}°C" + RESET)
        else:
            print(RED + "No valid results were found during benchmarking." + RESET)

# Add this new function to handle cleanup
def cleanup_and_exit(reason=None):
    global system_reset_done
    if system_reset_done:
        return
        
    try:
        if results:
            reset_to_best_setting()
            save_results()
            print(GREEN + "Bitaxe reset to best settings and results saved." + RESET)
        else:
            print(YELLOW + "No valid benchmarking results found. Applying predefined default settings." + RESET)
            set_system_settings(default_voltage, default_frequency)
    finally:
        system_reset_done = True
        if reason:
            print(RED + f"Benchmarking stopped: {reason}" + RESET)
        print(GREEN + "Benchmarking completed." + RESET)
        sys.exit(0)

