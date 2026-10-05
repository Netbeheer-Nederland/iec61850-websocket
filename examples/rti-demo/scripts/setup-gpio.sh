#!/usr/bin/env bash
set -euo pipefail

# Raspberry Pi 5 GPIO simulation for Linux Mint x86_64.
#
# Creates five virtual GPIO controllers using the Linux
# gpio-sim kernel module.
#
# Exposes the RP1 controller through two container device
# names: /dev/gpiochip0 and /dev/gpiochip4.

CONFIG_ROOT="/sys/kernel/config/gpio-sim"
ENV_FILE=".env.gpio"

if [[ $EUID -ne 0 ]]; then
    echo "Run this script using sudo."
    exit 1
fi

# -----------------------------------------------------------
# 1. Load kernel modules
# -----------------------------------------------------------

modprobe configfs

if ! mountpoint -q /sys/kernel/config; then
    mount -t configfs configfs /sys/kernel/config
fi

modprobe gpio-sim

if [[ ! -d "$CONFIG_ROOT" ]]; then
    echo "ERROR: gpio-sim configfs interface not available."
    exit 1
fi

# -----------------------------------------------------------
# 2. Create or reuse a simulated GPIO controller
# -----------------------------------------------------------

create_gpiochip() {
    local name="$1"
    local lines="$2"
    local label="$3"

    local device_dir="$CONFIG_ROOT/$name"
    local bank_dir="$device_dir/bank0"
    local chip_name
    local device_path

    if [[ ! -d "$device_dir" ]]; then

        echo "Creating $name ($lines GPIO lines)" >&2

        mkdir "$device_dir"
        mkdir "$bank_dir"

        echo "$lines" > "$bank_dir/num_lines"
        echo "$label" > "$bank_dir/label"

        # Instantiate the virtual GPIO controller.
        echo 1 > "$device_dir/live"

    else
        echo "Reusing existing controller: $name" >&2

        if [[ "$(cat "$device_dir/live")" != "1" ]]; then
            echo 1 > "$device_dir/live"
        fi
    fi

    # Obtain the actual Linux GPIO character-device name.
    chip_name=$(cat "$bank_dir/chip_name")

    if [[ ! "$chip_name" =~ ^gpiochip[0-9]+$ ]]; then
        echo "ERROR: Invalid GPIO chip name: $chip_name" >&2
        return 1
    fi

    device_path="/dev/$chip_name"

    # Allow udev to create the device node.
    udevadm settle

    local attempt
    for attempt in {1..20}; do
        if [[ -c "$device_path" ]]; then
            printf '%s\n' "$device_path"
            return 0
        fi
        sleep 0.1
    done

    echo "ERROR: Device not found: $device_path" >&2
    return 1
}

# -----------------------------------------------------------
# 3. Create the five independent virtual controllers
# -----------------------------------------------------------

RP1=$(create_gpiochip \
    "rpi5-rp1" 54 "pinctrl-rp1")

SOC10=$(create_gpiochip \
    "rpi5-soc10" 32 "gpio-brcmstb-10")

SOC11=$(create_gpiochip \
    "rpi5-soc11" 4 "gpio-brcmstb-11")

SOC12=$(create_gpiochip \
    "rpi5-soc12" 17 "gpio-brcmstb-12")

SOC13=$(create_gpiochip \
    "rpi5-soc13" 6 "gpio-brcmstb-13")

# -----------------------------------------------------------
# 4. Generate Docker Compose environment variables
# -----------------------------------------------------------

cat > "$ENV_FILE" <<EOF
GPIO_RP1=$RP1
GPIO_SOC10=$SOC10
GPIO_SOC11=$SOC11
GPIO_SOC12=$SOC12
GPIO_SOC13=$SOC13
EOF

chmod 644 "$ENV_FILE"

echo
echo "Raspberry Pi 5 GPIO simulation:"
echo
echo "Container device       Host device"
echo "----------------------------------------"
printf '%-22s %s\n' "/dev/gpiochip0" "$RP1"
printf '%-22s %s\n' "/dev/gpiochip4" "$RP1"
printf '%-22s %s\n' "/dev/gpiochip10" "$SOC10"
printf '%-22s %s\n' "/dev/gpiochip11" "$SOC11"
printf '%-22s %s\n' "/dev/gpiochip12" "$SOC12"
printf '%-22s %s\n' "/dev/gpiochip13" "$SOC13"

echo
echo "Generated: $ENV_FILE"
echo
echo "Available GPIO controllers:"
gpiodetect
