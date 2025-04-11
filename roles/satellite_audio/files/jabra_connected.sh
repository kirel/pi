#!/bin/bash

LOG_FILE="/var/log/jabra_connected.log"

# Function to log messages with a timestamp
log_message() {
    echo "$(date) - $1" >> "$LOG_FILE"
}

# Log the action
log_message "Jabra connected. Running commands..."

# Wait for the device to initialize
sleep 2

# Set default sink and source
SINK="alsa_output.usb-0b0e_Jabra_SPEAK_510_USB_745C4B6665B1021800-00.analog-stereo"
SOURCE="alsa_input.usb-0b0e_Jabra_SPEAK_510_USB_745C4B6665B1021800-00.mono-fallback"

log_message "Setting default sink to $SINK..."
if pactl set-default-sink "$SINK"; then
    log_message "Successfully set default sink."
else
    log_message "Failed to set default sink."
fi

log_message "Setting volume of $SINK..."
if pactl set-sink-volume "$SINK" 74%; then
    log_message "Successfully set volume of $SINK."
else
    log_message "Failed to set volume of $SINK."
fi

log_message "Setting default source to $SOURCE..."
if pactl set-default-source "$SOURCE"; then
    log_message "Successfully set default source."
else
    log_message "Failed to set default source."
fi

# Restart all Docker containers with 'wyoming' in their name
log_message "Restarting Docker containers with 'wyoming' in their name..."
if docker ps --filter "name=wyoming" --format "{{ .Names }}" | xargs -r docker restart; then
    log_message "Docker containers restarted successfully."
else
    log_message "Failed to restart Docker containers."
fi

log_message "Script execution completed."
