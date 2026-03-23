#!/usr/bin/env bash

dry_run=false

# Parse args
for arg in "$@"; do
    case "$arg" in
        --dry-run) dry_run=true ;;
    esac
done

# Choose output
if $dry_run; then
    echo "DRY RUN"
    exec 3> /dev/null
else
    exec 3> /tmp/sut_pipe
fi

# Function to send arbitrary-length byte arrays
send_payload() {
    local bytes=("$@")
    local hex_str=""
    local oct_byte
    for b in "${bytes[@]}"; do
        ((b=b&0xFF))             # Ensure valid byte
        printf -v hex_byte "%02x" "$b"
        hex_str+="$hex_byte "     # For dry-run
        # Write raw byte using octal (safe)
        printf "\\$(printf '%03o' "$b")" >&3
    done
    echo "$hex_str"
    sleep 1
}

# Send init message.
send_payload 0 0x42 0

for i in {1..30}; do
    # Send status/Poll status
    send_payload 0 0 0x5 0x10 0 0 0 0
done

# Close fd
exec 3>&-
