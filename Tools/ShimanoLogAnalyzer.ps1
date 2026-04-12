# ShimanoLogAnalyzer.ps1 — GUI tool for analyzing Shimano UART logs
# Paste R:/R2: log lines, click Analyze, get decoded output side by side.

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# ---------- CRC-16/X-25 ----------
function Get-CRC16X25([byte[]]$data) {
    [uint16]$crc = 0xFFFF
    foreach ($b in $data) {
        $crc = $crc -bxor $b
        for ($i = 0; $i -lt 8; $i++) {
            if ($crc -band 1) {
                $crc = ($crc -shr 1) -bxor 0x8408
            } else {
                $crc = $crc -shr 1
            }
        }
    }
    return $crc -bxor 0xFFFF
}

# ---------- DECODE ----------
function Decode-ShimanoLine([string]$line) {
    $line = $line.Trim()
    if (-not $line) { return "" }

    # Extract channel prefix and hex bytes
    $channel = ""
    $hexPart = $line
    if ($line -match '^(R2?:)\s*(.+)$') {
        $channel = $Matches[1]
        $hexPart = $Matches[2]
    } elseif ($line -match '^(B-[TR]X:)\s*(.+)$') {
        $channel = $Matches[1]
        $hexPart = $Matches[2]
    } else {
        return "-- not a log line --"
    }

    # Channel label
    switch ($channel) {
        "R:"    { $chLabel = "Battery TX" }
        "R2:"   { $chLabel = "Charger/Motor TX" }
        "B-TX:" { $chLabel = "Battery TX" }
        "B-RX:" { $chLabel = "Charger/Motor TX" }
        default { $chLabel = $channel }
    }

    # Parse hex bytes
    $tokens = $hexPart.Trim() -split '\s+'
    $bytes = @()
    foreach ($t in $tokens) {
        $t = $t.Trim()
        if ($t -match '^[0-9A-Fa-f]{2}$') {
            $bytes += [byte]([Convert]::ToByte($t, 16))
        }
    }

    if ($bytes.Count -lt 5) {
        return "[$chLabel] Too short ($($bytes.Count) bytes)"
    }

    # Prefix
    $prefix = $bytes[0]
    if ($prefix -ne 0x00) {
        return "[$chLabel] Invalid prefix: 0x$("{0:X2}" -f $prefix)"
    }

    # Header
    $header = $bytes[1]
    $senderNibble = ($header -band 0xF0)
    $seq = ($header -band 0x0F)

    switch ($senderNibble) {
        0x00 { $sender = "Charger" }
        0x40 { $sender = "Charger (Handshake)" }
        0x80 { $sender = "Battery" }
        0xC0 { $sender = "Battery (Handshake)" }
        default { $sender = "0x$("{0:X2}" -f $senderNibble)" }
    }

    $length = $bytes[2]
    $expectedTotal = 3 + $length + 2

    # CRC check
    $crcOk = ""
    if ($bytes.Count -ge $expectedTotal) {
        $crcLo = $bytes[$expectedTotal - 2]
        $crcHi = $bytes[$expectedTotal - 1]
        $crcReceived = [uint16]($crcLo) + [uint16]($crcHi -shl 8)
        if ($crcReceived -eq 0x0000) {
            $crcOk = "CRC=0000 (ack)"
        } else {
            $crcData = $bytes[1..($expectedTotal - 3)]
            $crcCalc = Get-CRC16X25 $crcData
            if ($crcCalc -eq $crcReceived) {
                $crcOk = "CRC OK"
            } else {
                $crcOk = "CRC ERROR (got $("{0:X4}" -f $crcReceived), calc $("{0:X4}" -f $crcCalc))"
            }
        }
    } elseif ($bytes.Count -lt $expectedTotal) {
        $crcOk = "INCOMPLETE ($($bytes.Count)/$expectedTotal bytes)"
    }

    # Length=0: Handshake / Ping / Ack
    if ($length -eq 0) {
        $type = ""
        if ($senderNibble -eq 0x40 -or $senderNibble -eq 0xC0) {
            $type = "Handshake"
        } else {
            # Check CRC
            $crcLo = $bytes[3]; $crcHi = $bytes[4]
            $crcVal = [uint16]($crcLo) + [uint16]($crcHi -shl 8)
            if ($crcVal -eq 0x0000) {
                $type = "Ack (CRC=0000)"
            } else {
                $type = "Ping"
            }
        }
        return "[$chLabel] $sender Seq=$seq | $type | $crcOk"
    }

    # Payload present
    $payload = $bytes[3..(3 + $length - 1)]
    $cmd = $payload[0]
    $cmdHex = "0x$("{0:X2}" -f $cmd)"

    # --- Cmd 0x10: Telemetry ---
    if ($cmd -eq 0x10) {
        # Poll (Length=5)
        if ($length -eq 5) {
            $pollByte1 = $payload[1]
            $pollByte2 = $payload[2]
            $pollInfo = ""
            if ($pollByte1 -eq 0x00 -and $pollByte2 -eq 0x00) {
                $pollInfo = "Charger poll"
            } elseif ($pollByte1 -eq 0x02 -and $pollByte2 -eq 0x02) {
                $pollInfo = "Motor poll (boot)"
            } elseif ($pollByte1 -eq 0x03 -and $pollByte2 -eq 0x03) {
                $pollInfo = "Motor poll (ready)"
            } elseif ($pollByte1 -eq 0x04) {
                $pollInfo = "Charger poll (init flag 0x04)"
            } else {
                $pollInfo = "Poll (p1=0x$("{0:X2}" -f $pollByte1) p2=0x$("{0:X2}" -f $pollByte2))"
            }
            return "[$chLabel] $sender Seq=$seq | Cmd 0x10 $pollInfo | $crcOk"
        }

        # Telemetry response (Length=22)
        if ($length -eq 22 -and $payload.Count -ge 22) {
            $unknown1  = $payload[1]
            $state     = $payload[2]
            $unk3      = $payload[3]
            $unk4      = $payload[4]
            $unk5      = $payload[5]

            $packV     = [uint16]($payload[6]) + [uint16]($payload[7] -shl 8)
            $cellMax   = ([uint16]($payload[8]) + [uint16]($payload[9] -shl 8)) / 2.0
            $cellMin   = ([uint16]($payload[10]) + [uint16]($payload[11] -shl 8)) / 2.0
            $cellSpread = $cellMax - $cellMin
            $ntcMax    = $payload[12]
            $ntcAvg    = $payload[13]
            $th002     = $payload[14]
            $soc       = $payload[15]
            $chargeCtr = $payload[16]
            $off17     = $payload[17]
            $off18     = $payload[18]

            # State name
            switch ($state) {
                0x00 { $stName = "Init" }
                0x01 { $stName = "Active (Motor)" }
                0x02 { $stName = "Precharge" }
                0x03 { $stName = "Charging" }
                default { $stName = "0x$("{0:X2}" -f $state)" }
            }

            # Fault flag
            $faultInfo = ""
            if ($unknown1 -ne 0x00) {
                $faultInfo = " FAULT=0x$("{0:X2}" -f $unknown1)"
            }
            # Unknown bytes 3-5
            $unkInfo = ""
            if ($unk3 -ne 0 -or $unk4 -ne 0 -or $unk5 -ne 0) {
                $unkInfo = " Unk3-5=$("{0:X2}" -f $unk3)/$("{0:X2}" -f $unk4)/$("{0:X2}" -f $unk5)"
            }

            $voltStr = "$packV mV ($("{0:N1}" -f ($packV / 1000.0))V)"
            $cellStr = "Cmax=$([int]$cellMax) Cmin=$([int]$cellMin) D=$([int]$cellSpread)mV"
            $tempStr = "T=$ntcMax/$ntcAvg/${th002}C"

            $extra = ""
            if ($off17 -ne 0 -or $off18 -ne 0) {
                $extra = " | Off17=0x$("{0:X2}" -f $off17) Off18=0x$("{0:X2}" -f $off18)"
            }

            $result = "[$chLabel] $sender Seq=$seq | Telemetry State=$stName$faultInfo$unkInfo | $voltStr | $cellStr | $tempStr | SOC=${soc}% | ChgCtr=$chargeCtr$extra | $crcOk"
            return $result
        }

        # Other Length for Cmd 0x10
        $payloadHex = ($payload | ForEach-Object { "{0:X2}" -f $_ }) -join " "
        return "[$chLabel] $sender Seq=$seq | Cmd 0x10 Len=$length | $payloadHex | $crcOk"
    }

    # --- Cmd 0x11: Device Info ---
    if ($cmd -eq 0x11) {
        if ($length -eq 1) {
            return "[$chLabel] $sender Seq=$seq | Cmd 0x11 Device Info Request | $crcOk"
        }
        if ($length -eq 9 -and $payload.Count -ge 9) {
            $payloadHex = ($payload | ForEach-Object { "{0:X2}" -f $_ }) -join " "
            $val1 = $payload[2]
            $fw1 = $payload[4]; $fw2 = $payload[5]
            return "[$chLabel] $sender Seq=$seq | Cmd 0x11 Device Info Response | Byte2=0x$("{0:X2}" -f $val1) FW?=0x$("{0:X2}" -f $fw1)$("{0:X2}" -f $fw2) | $payloadHex | $crcOk"
        }
        $payloadHex = ($payload | ForEach-Object { "{0:X2}" -f $_ }) -join " "
        return "[$chLabel] $sender Seq=$seq | Cmd 0x11 Len=$length | $payloadHex | $crcOk"
    }

    # --- Cmd 0x21: Shutdown ---
    if ($cmd -eq 0x21) {
        if ($length -eq 1) {
            return "[$chLabel] $sender Seq=$seq | Cmd 0x21 Shutdown Request | $crcOk"
        }
        if ($length -eq 3) {
            return "[$chLabel] $sender Seq=$seq | Cmd 0x21 Shutdown Ack | $crcOk"
        }
        $payloadHex = ($payload | ForEach-Object { "{0:X2}" -f $_ }) -join " "
        return "[$chLabel] $sender Seq=$seq | Cmd 0x21 Len=$length | $payloadHex | $crcOk"
    }

    # --- Cmd 0x32: Trip/Config ---
    if ($cmd -eq 0x32) {
        $payloadHex = ($payload | ForEach-Object { "{0:X2}" -f $_ }) -join " "
        return "[$chLabel] $sender Seq=$seq | Cmd 0x32 Trip/Config Len=$length | $payloadHex | $crcOk"
    }

    # --- Unknown command ---
    $payloadHex = ($payload | ForEach-Object { "{0:X2}" -f $_ }) -join " "
    return "[$chLabel] $sender Seq=$seq | Cmd $cmdHex Len=$length | $payloadHex | $crcOk"
}

# ---------- GUI ----------
$form = New-Object System.Windows.Forms.Form
$form.Text = "Shimano UART Log Analyzer"
$form.Size = New-Object System.Drawing.Size(1400, 700)
$form.StartPosition = "CenterScreen"
$form.MinimumSize = New-Object System.Drawing.Size(900, 400)
$form.Font = New-Object System.Drawing.Font("Segoe UI", 9)

# Top label
$lblInput = New-Object System.Windows.Forms.Label
$lblInput.Text = "Paste log lines (R: / R2: / B-TX: / B-RX:):"
$lblInput.Location = New-Object System.Drawing.Point(10, 8)
$lblInput.AutoSize = $true
$form.Controls.Add($lblInput)

$lblOutput = New-Object System.Windows.Forms.Label
$lblOutput.Text = "Decoded:"
$lblOutput.AutoSize = $true
$form.Controls.Add($lblOutput)

# Monospace font for text boxes
$monoFont = New-Object System.Drawing.Font("Consolas", 10)

# Input textbox (left)
$txtInput = New-Object System.Windows.Forms.TextBox
$txtInput.Multiline = $true
$txtInput.ScrollBars = "Both"
$txtInput.WordWrap = $false
$txtInput.Font = $monoFont
$txtInput.AcceptsReturn = $true
$form.Controls.Add($txtInput)

# Output textbox (right)
$txtOutput = New-Object System.Windows.Forms.TextBox
$txtOutput.Multiline = $true
$txtOutput.ScrollBars = "Both"
$txtOutput.WordWrap = $false
$txtOutput.Font = $monoFont
$txtOutput.ReadOnly = $true
$txtOutput.BackColor = [System.Drawing.Color]::FromArgb(245, 245, 245)
$form.Controls.Add($txtOutput)

# Analyze button
$btnAnalyze = New-Object System.Windows.Forms.Button
$btnAnalyze.Text = "Analyze"
$btnAnalyze.Size = New-Object System.Drawing.Size(100, 30)
$btnAnalyze.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$btnAnalyze.BackColor = [System.Drawing.Color]::FromArgb(0, 120, 212)
$btnAnalyze.ForeColor = [System.Drawing.Color]::White
$btnAnalyze.FlatStyle = "Flat"
$form.Controls.Add($btnAnalyze)

# Clear button
$btnClear = New-Object System.Windows.Forms.Button
$btnClear.Text = "Clear"
$btnClear.Size = New-Object System.Drawing.Size(70, 30)
$btnClear.FlatStyle = "Flat"
$form.Controls.Add($btnClear)

# Status label
$lblStatus = New-Object System.Windows.Forms.Label
$lblStatus.AutoSize = $true
$lblStatus.ForeColor = [System.Drawing.Color]::Gray
$form.Controls.Add($lblStatus)

# Layout on resize
$form.Add_Resize({
    $w = $form.ClientSize.Width
    $h = $form.ClientSize.Height
    $btnY = 32
    $topOffset = 60
    $bottomMargin = 10
    $gap = 10
    $halfW = [Math]::Floor(($w - 30) / 2)
    $boxH = $h - $topOffset - $bottomMargin

    $txtInput.Location = New-Object System.Drawing.Point(10, $topOffset)
    $txtInput.Size = New-Object System.Drawing.Size($halfW, $boxH)

    $lblOutput.Location = New-Object System.Drawing.Point(($halfW + 20), 8)

    $txtOutput.Location = New-Object System.Drawing.Point(($halfW + 20), $topOffset)
    $txtOutput.Size = New-Object System.Drawing.Size($halfW, $boxH)

    $btnAnalyze.Location = New-Object System.Drawing.Point(($w - 300), $btnY)
    $btnClear.Location = New-Object System.Drawing.Point(($w - 190), $btnY)
    $lblStatus.Location = New-Object System.Drawing.Point(($w - 110), ($btnY + 6))
})

# Trigger initial layout
$form.Add_Shown({ $form.GetType().GetMethod('OnResize', [System.Reflection.BindingFlags]'NonPublic,Instance').Invoke($form, @([System.EventArgs]::Empty)) })

# Analyze click handler
$btnAnalyze.Add_Click({
    $lines = $txtInput.Text -split "`r?`n"
    $results = @()
    $decoded = 0
    foreach ($rawLine in $lines) {
        $trimmed = $rawLine.Trim()
        if (-not $trimmed) {
            $results += ""
            continue
        }
        $result = Decode-ShimanoLine $trimmed
        $results += $result
        if ($result -and $result -ne "-- not a log line --") { $decoded++ }
    }
    $txtOutput.Text = $results -join "`r`n"
    $lblStatus.Text = "$decoded lines decoded"
    $lblStatus.ForeColor = [System.Drawing.Color]::FromArgb(0, 120, 50)
})

# Clear click handler
$btnClear.Add_Click({
    $txtInput.Text = ""
    $txtOutput.Text = ""
    $lblStatus.Text = ""
})

# Synchronized scrolling: scroll output when input scrolls
$scrolling = $false
$txtInput.Add_KeyUp({
    if (-not $scrolling) {
        $scrolling = $true
        $line = $txtInput.GetLineFromCharIndex($txtInput.GetCharIndexFromPosition([System.Drawing.Point]::new(0, 0)))
        $charIdx = $txtOutput.GetFirstCharIndexFromLine([Math]::Min($line, $txtOutput.Lines.Count - 1))
        if ($charIdx -ge 0) {
            $txtOutput.SelectionStart = $charIdx
            $txtOutput.ScrollToCaret()
        }
        $scrolling = $false
    }
})

[void]$form.ShowDialog()
