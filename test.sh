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
    sleep 0.5
}

send_payload 0x42 0

# Example usage
for i in {0..15}; do
    for j in {0..15}; do
	payload=( $(((i << 4) + j)) 0 )  # Decimal bytes
        send_payload "${payload[@]}"
    done
done

# Close fd
exec 3>&-
