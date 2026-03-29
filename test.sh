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

# INIT
send_payload 0 0x40 0 0 0
# STATUS
send_payload 0 1 5 0x10 0 0 0 0 0 0

# ?
send_payload 0x00 0x02 0x11 0x30 0x02 0x01 0x9E 0x9E 0x9E 0x9F 0xF6 0xF6 0xF6 0xF6 0x9F 0x9F 0x9F 0x9F 0xD0 0x08 0 0
# ?
send_payload 0x00 0x03 0x0B 0x31 0x9F 0x01 0xA9 0x01 0x01 0x00 0x02 0x00 0x1F 0x00 0 0

# TIMESTAMP
send_payload 0 4 7 0x32 0x19 9 5 0x0E 0x0D 0 0 0

# Close fd
exec 3>&-
