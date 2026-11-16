# LEIBINGER JET3 On-Site Commissioning Guide

**Initial state: all physical-printer commissioning tests are NOT TESTED.**  
This guide is for an operator to execute manually, one step at a time. Record results only after each step has actually been completed and confirmed. Do not infer a pass from an unexecuted check or from a TCP connection alone.

## 1. Scope and safety

This guide covers the existing Phase 1 manual terminal application and the first controlled ASCII ExternText test. It does not authorize production operation, automatic Lot updates, job upload, printer-state changes, or a print start.

For the first physical write, the project’s commissioning policy is to keep production stopped, prevent print triggers, use a prepared non-Unicode test job, and have one controller changing ExternText. This is a project safety policy; the supplied manuals do not establish that stopping printing is an ExternText protocol requirement. The application does not check or enforce printer state.

- Do not assign an IP until the site network administrator confirms its reservation and availability.
- Do not use a factory reset to resolve interface-mode or protocol problems.
- Do not blindly repeat a failed or timed-out write: delivery may be unknown. Read the value and inspect the printer before deciding what to do.
- `SENT - UNVERIFIED` means the application completed a socket write; it is **not proof of printer acceptance**.
- `VERIFIED` means the value returned by `?ET` exactly matched the value previously sent; it **does not prove successful physical printing**, correct job usage, or correct product marking.

## 2. Intended network configuration

| Item | Commissioning value |
|---|---|
| Server address | `172.28.169.254` |
| JET3 printer address | `172.28.169.248` |
| TCP port | `3000` |
| Network path | Server → WAGO Switch → JET3 |
| Physical connection | M12 D-coded 4-pin Ethernet to RJ45 |

Confirm the server address is assigned to the intended factory/Machine network interface and that the route to the printer uses that interface. Confirm subnet mask, routing, and any access-control/firewall requirements with the site network administrator. The application relies on the operating system route; it does not bind to or configure a network adapter.

The Jet3 manual’s example IP is not this commissioning address. The printer’s actual IP, subnet mask, Ethernet selection, and port must be checked at the printer. The project’s local `.env` is not documented here; confirm the target shown in the application before connecting. The versioned [.env.example](../.env.example) contains a blank IP placeholder.

### Suggested Windows checks (operator-run; not performed for this guide)

1. Check the server NIC configuration with `ipconfig` and the route with `route print`.
2. Check physical link indicators and cable seating along the M12-to-RJ45 and WAGO switch path.
3. An optional `ping 172.28.169.248` can help diagnose reachability. A ping timeout alone does not prove the address is unused or that TCP is unavailable; ICMP may be disabled.
4. Check the TCP listener with PowerShell `Test-NetConnection -ComputerName 172.28.169.248 -Port 3000`. A successful `TcpTestSucceeded` confirms a TCP handshake to that address and port, not printer identity, Jet3 protocol support, or readiness.

## 3. Application architecture and startup

The Phase 1 application is a Python 3.11, standard-library-only terminal tool. It supports manually configuring a target, testing TCP, reading ExternText, sending ASCII ExternText, and comparing a readback. It does not implement SQL, automatic Lot monitoring, product/color lookup, printer job upload, print start/stop, or arbitrary raw commands.

- [lj3/config.py](../lj3/config.py): loads and validates the project-local `.env` subset `LJ3_IP`, `LJ3_PORT`, and `LJ3_TIMEOUT_SECONDS`. Defaults are no IP, port 3000, and a 3-second timeout. Valid ports are 1–65535 and timeout is 0.1–60 seconds. Menu changes are session-only.
- [lj3/protocol.py](../lj3/protocol.py): builds allowlisted `=ET` and `?ET` frames, validates ASCII text, parses incoming frames, and decodes ExternText.
- [lj3/client.py](../lj3/client.py): `LJ3Client.connect()` opens TCP; `send_command()` sends an allowed command; `_read_external_text_frame()` receives and validates replies; `set_external_text()`, `get_external_text()`, and `verify_external_text()` provide the higher-level actions.
- [lj3/__main__.py](../lj3/__main__.py): displays the menu and runs actions explicitly chosen by the operator. Startup itself performs no network I/O.

From PowerShell opened in the project directory, the documented launch is:

```powershell
.\.venv\Scripts\python.exe -m lj3
```

[Inkjet.bat](../Inkjet.bat) is an alternative launcher using the project virtual environment. Run it from the project directory because its paths are relative. At startup, confirm that the displayed printer target is `172.28.169.248:3000`. If a session correction is needed, use menu option 6; it does not change `.env` or configure the server NIC. Do not overwrite or otherwise alter the existing `.env` as part of this guide.

The menu and call flow are in [lj3/__main__.py](../lj3/__main__.py#L26-L46); startup instructions are in [README.md](../README.md#L8-L17).

## 4. Menu options

| Option | Function | Input and output | Prerequisites / limitations |
|---|---|---|---|
| **1 — Test TCP Connection** | Calls `connect()`, reports `TCP CONNECTION OK` or `TCP CONNECTION FAILED`, then disconnects. | No command payload. | Valid target and route. TCP success does not prove printer identity or Jet3 command support. |
| **2 — Read Current ExternText** | Calls `get_external_text()`, sends `?ET`, and displays the returned value. | No operator text input; terminal displays the current returned value. | Reachable printer and supported/valid response. This is a read operation and does not change ExternText. |
| **3 — Send Test Text (TEST123)** | Previews fixed `TEST123`, asks for confirmation, and calls `set_external_text()` once. | Type exactly `SEND` to proceed; other input cancels. | This writes to the printer. Confirm production is stopped and the correct non-Unicode Field 0 test job is loaded first. No automatic readback follows. |
| **4 — Verify Last Sent Text** | Calls `verify_external_text()` to perform a separate `?ET` read and exact string comparison. | Displays sent value, readback, and `VERIFIED`, `MISMATCH`, or `COMMUNICATION ERROR`. | Requires a successful write in this target/session. A target change or failed write clears/invalidates comparison history. Does not write or print. |
| **5 — Send Free Text** | Prompts for operator text, previews it, and sends once after confirmation. | Printable ASCII only; type exactly `SEND`. | This writes to the printer. Empty text, controls, non-ASCII, and literal backslashes are rejected. Carets are escaped. Check job length/offset before writing. |
| **6 — Configure Target** | Prompts for printer IPv4, TCP port, and timeout. | Blank input keeps the current value. | Values are validated; configuration is session-only and clears verification history. Does not configure the server NIC. |
| **0 — Quit** | Exits and closes any local socket. | No further input. | If an operation was interrupted, the printer may have received some or all of a write; there is no automatic retry. |

## 5. JET3 protocol and printer job requirements

### Frame and command behavior

The interface protocol uses `^` + ASCII destination address + command and parameters + final CR. The printer address is ASCII `0` (`0x30`), not binary zero. Optional LF may follow CR; the application sends CR only. A caret in data is escaped as `\^`. Ordinary command packets do not have a guaranteed direct acknowledgement.

- **Write:** `=ET` sets ExternText. The application frame for `TEST123` is `^0=ETTEST123<CR>`; the final byte is CR (`0x0D`).
- **Read:** `?ET` requests ExternText. The expected ordinary response, based on the manual’s general inquiry rule, is `^0=ET<value><CR>`. A five-digit length-prefixed response is also supported by the parser.
- **Verification:** the application opens a fresh TCP connection for the readback and compares exact strings. Spaces are preserved; they are not stripped or normalized.
- **No write acknowledgement:** a successful `sendall()` is not proof the Jet3 accepted the value. The application labels the result `SENT - UNVERIFIED`; it does not wait for an undocumented write ACK.

The manual lists `?ET` and the general `?XX` → `=XX` inquiry rule, but gives no dedicated `?ET` response example or minimum firmware version. Therefore, support and actual response format are commissioning checks, not guaranteed by the application.

`LJ3Client.connect()` is the TCP handshake; `send_command()` sends; `_read_external_text_frame()` receives and validates; `set_external_text()` writes; `get_external_text()` reads; and `verify_external_text()` compares. See [lj3/client.py](../lj3/client.py#L69-L83), [lj3/client.py](../lj3/client.py#L95-L201), and [lj3/protocol.py](../lj3/protocol.py#L14-L118).

### Printer-side setup

At the Jet3, check the following using its local controls and the installed job:

1. **Network:** under Settings / Basic settings / IP_Adress, verify IP `172.28.169.248` and the site-approved subnet mask.
2. **Interface:** under Extra / Interface settings / Connection Typ, select Ethernet and confirm port `3000`.
3. **Power/state:** the interface manual says its command definitions apply to a turned-on device; standby handling is limited. The application does not read or enforce machine state.
4. **Job:** load a suitable job locally containing an external-text object using `{e}` / EXTTXT and **Field Number 0**. Mailing fields 1+ are not the ExternText field.
5. **Text layout:** verify each relevant object's placeholder length and character offset. The largest offset-plus-placeholder count across objects determines the job’s required input length. Confirm that `TEST123` (7 characters) fits the loaded test job.
6. **Font:** use a non-Unicode font for this ASCII test. Unicode fonts require a different hexadecimal representation according to the interface manual; this application blocks non-ASCII input.
7. **Double-print checking:** establish the intended Check double prints setting with the responsible operator. The script manual says missing new external text after PrintGo can stop printing and generate an error when this setting is enabled.
8. **Interface modes:** use normal unpadded output. The client does not configure echo, length mode, CRC, or other printer interface state. It accepts a length header but does not support fixed-block space padding.
9. **Exclusive writer:** ensure no other controller changes ExternText during the test. The protocol provides no transaction IDs or concurrent-writer protection.

Manual references: [manual/Manual_LJ3_Interfaceprotocol.pdf](../manual/Manual_LJ3_Interfaceprotocol.pdf), [manual/Manual_LJ3_Scriptlanguage.pdf](../manual/Manual_LJ3_Scriptlanguage.pdf), [manual/ManualHyperterminalLJ3Engl.pdf](../manual/ManualHyperterminalLJ3Engl.pdf), with searchable extracts under [docs/manual-extracted](manual-extracted). The PDFs are authoritative if extracted text differs.

## 6. Numbered commissioning checklist

Perform each step manually and in order. **Stop after completing a step, record its result, and obtain the commissioning lead’s approval before starting the next step.** “Pass” requires observing the stated result; otherwise record “Fail” or “Blocked” and the evidence. Do not mark an unperformed physical test as passed.

### A. Read-only checks and preparation

These steps inspect configuration or perform connectivity/read operations. They do not issue an ExternText write. TCP checks still open a network connection; option 2 sends the read-only `?ET` inquiry.

1. **Confirm scope and address assignment.** Confirm printer identity, address reservation, and site authorization with the network administrator. Verify the intended addresses: server `172.28.169.254`, printer `172.28.169.248`, port `3000`; confirm the WAGO switch path and intended server NIC.  
   **Expected:** address assignment and route are confirmed by the responsible site contact.  
   **Pass:** confirmations and intended interface are recorded. **Fail/Blocked:** reservation or route is uncertain; do not proceed to connect.
2. **Inspect printer Ethernet configuration.** At the Jet3, inspect IP, subnet mask, Ethernet selection, and port using local controls. Do not change settings unless separately authorized.  
   **Expected:** printer shows the approved `172.28.169.248` address, compatible subnet, Ethernet, and port `3000`.  
   **Pass:** all values match and are recorded. **Fail:** any value differs. **Blocked:** not available to inspect.
3. **Check physical/network path.** Inspect the M12 D-coded 4-pin to RJ45 connection, WAGO switch link indications, server NIC configuration, and route. Optionally ping the printer; a missing ping response is inconclusive.  
   **Expected:** physical links are present and the server route uses the intended factory/Machine NIC.  
   **Pass:** link and route evidence are recorded. **Fail/Blocked:** link or route is absent/uncertain; do not continue to application TCP testing.
4. **Test TCP port 3000 from the server.** Run the operator-approved TCP test, such as `Test-NetConnection -ComputerName 172.28.169.248 -Port 3000`.  
   **Expected:** `TcpTestSucceeded` is `True`.  
   **Pass:** TCP handshake succeeds and target/port are recorded. **Fail:** handshake fails; troubleshoot before proceeding. This does not identify the device or test `?ET`/`=ET`.
5. **Launch the application and check its target.** From the project directory run the PowerShell command shown in the startup section above, or launch [Inkjet.bat](../Inkjet.bat). Verify the displayed target is `172.28.169.248:3000`. Use option 6 only if a session correction is needed.  
   **Expected:** menu appears without an automatic connection, and displayed target is correct.  
   **Pass:** both conditions are observed. **Fail/Blocked:** startup/configuration error or incorrect target; do not connect until resolved.
6. **Test TCP in the application (option 1).** Select **1 Test TCP Connection**.  
   **Expected:** `TCP CONNECTION OK`, followed by disconnection; no Jet3 command is transmitted.  
   **Pass:** exact success is displayed. **Fail:** `TCP CONNECTION FAILED` or an error; record message and stop. TCP success alone does not prove printer identity/readiness.
7. **Read baseline ExternText (option 2).** Select **2 Read Current ExternText** and record the displayed value and terminal TX/RX evidence.  
   **Expected:** a valid `=ET` readback is displayed, possibly empty if the printer reports an empty value.  
   **Pass:** a valid response is received and recorded. **Fail/Blocked:** timeout, peer close, or protocol error; do not infer empty text or unsupported firmware solely from timeout.

### B. Write test — requires explicit operator approval

Do not begin this section unless read-only steps 1–7 have passed, the responsible operator confirms printing is stopped and triggers are prevented, and the test job is prepared. These steps change printer ExternText.

8. **Prepare the safe test job locally.** Confirm a non-Unicode Field 0 EXTTXT object, suitable placeholder length/offset for `TEST123`, expected visual layout, and agreed double-print-check setting. Confirm only one ExternText controller will be active.  
   **Expected:** job configuration is inspected and recorded; printing remains stopped.  
   **Pass:** operator and commissioning lead approve the prepared job. **Fail/Blocked:** do not write.
9. **Write fixed test text (option 3).** Select **3 Send Test Text (TEST123)**. Check target and byte preview. Type exactly `SEND` only after reconfirming the stopped-production and test-job conditions.  
   **Expected:** one `=ET` frame is attempted and the app reports `SENT - UNVERIFIED`.  
   **Pass for transport attempt only:** the app reports sent with no communication error. This is **not proof of printer acceptance**. **Fail/Uncertain:** any error or interruption; do not resend automatically. Inspect/read first.
10. **Read back and compare (option 4).** After a successful write attempt, select **4 Verify Last Sent Text**.  
    **Expected:** a separate `?ET` readback; exact `TEST123` gives `VERIFIED`, any difference gives `MISMATCH`, and read/protocol failure gives `COMMUNICATION ERROR`.  
    **Pass for value readback only:** `VERIFIED` and exact readback recorded. This **does not prove successful physical printing**. **Fail:** mismatch or communication error; preserve raw logs and troubleshoot.
11. **Close out without starting production.** Record printer identity/firmware, job/font/Field 0 details, actual TX/RX, app results, and any anomaly. Keep printing stopped unless the responsible site lead separately authorizes another controlled procedure. The application cannot start a print or verify physical output.

## 7. Commissioning results record

All physical-printer tests start as **NOT TESTED**. Update an entry only after that step is confirmed; include evidence in Notes. Use `PASS`, `FAIL`, or `BLOCKED` only when supported by an observed result.

| Step | Test | Expected Result | Actual Result | Status | Notes |
|---:|---|---|---|---|---|
| 1 | Address reservation, network path, and intended NIC | Site confirms addresses and route | — | **NOT TESTED** | |
| 2 | Printer IP/subnet/Ethernet/port inspection | `172.28.169.248`, approved subnet, Ethernet, port `3000` | — | **NOT TESTED** | |
| 3 | Physical link, server NIC, and route | Link present; intended route confirmed | — | **NOT TESTED** | |
| 4 | TCP port 3000 test | TCP handshake succeeds | — | **NOT TESTED** | |
| 5 | Application launch/target check | Menu opens without network I/O; target is correct | — | **NOT TESTED** | |
| 6 | Application option 1 TCP check | `TCP CONNECTION OK` | — | **NOT TESTED** | |
| 7 | Application option 2 baseline ExternText read | Valid `?ET` / `=ET` response recorded | — | **NOT TESTED** | |
| 8 | Safe stopped-production test job preparation | Non-Unicode Field 0 job suitable for `TEST123`; printing stopped | — | **NOT TESTED** | |
| 9 | Application option 3 write `TEST123` | Single write attempt; `SENT - UNVERIFIED` or error recorded | — | **NOT TESTED** | |
| 10 | Application option 4 exact readback | Exact readback `TEST123` → `VERIFIED`; otherwise mismatch/error recorded | — | **NOT TESTED** | |
| 11 | Closeout/physical-output authorization | Evidence recorded; no unapproved state change or print start | — | **NOT TESTED** | |

## 8. Troubleshooting and limitations

| Symptom | Checks and response |
|---|---|
| Network connection failure | Recheck address reservation, server NIC/IP, subnet/route, cable seating, switch link, printer Ethernet setting, and site network controls. A ping failure alone is inconclusive. |
| TCP connection failure | Confirm the displayed target and printer port, route/firewall policy, and printer power/state. Option 1 is only a TCP handshake. No retry is performed automatically. |
| `?ET` timeout or peer close | Preserve terminal output; check printer state, port, and interface configuration. A timeout is not proof that the value is empty or that firmware lacks `?ET`. The next operator action opens a fresh connection. |
| Protocol error | Preserve raw bytes and hex. Check frame start/address/CR, optional length header, unexpected controls, padding, incomplete or multiple replies, and interface mode. The parser fails closed; do not bypass it. |
| Unexpected printer response | The app logs unmatched frames; it recognizes `=FC` as CRC failure and nonzero error values in `=RS`. Consult the printer display/vendor documentation; do not invent meanings for other frames. |
| ExternText write failure | Delivery may be partial, complete, or unknown. Do not immediately resend. Read back and inspect the printer before deciding whether another write is appropriate. |
| ExternText read failure | Check TCP and printer state, then inspect the raw response. Unsupported `?ET` is one possibility, not a conclusion from a timeout alone. |
| Readback mismatch | Compare exact spaces and text; inspect competing writers, job font, Field 0, offsets, and placeholders. A successful readback does not establish correct physical output. |

Known limitations: no retries, transaction IDs, concurrency protection, automatic production/Lot workflow, SQL, job upload, printer state interlock, or physical print confirmation. Unicode writes are blocked. Fixed-block padded replies are unsupported. `?ET` firmware support, active-print update behavior, job/power-cycle persistence, print cutover timing, and physical output require separate on-site/vendor confirmation.

For the project’s existing procedure and evidence basis, see [README.md](../README.md), [docs/COMMISSIONING.md](COMMISSIONING.md), [docs/PROJECT_CONTEXT.md](PROJECT_CONTEXT.md), and the PDFs/extracts under [manual](../manual) and [docs/manual-extracted](manual-extracted).
