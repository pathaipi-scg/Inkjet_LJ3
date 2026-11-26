# LEIBINGER JET3 On-Site Commissioning Guide

Commissioning results are updated incrementally. Steps that have not been completed remain **NOT TESTED**. Record results only after a step has actually been completed and confirmed. Do not infer printer identity or readiness from a TCP connection alone.

## 1. Scope and safety

This guide covers the existing Phase 1 manual terminal application and controlled ASCII ExternText communication tests. Status inquiry and exact `TEST123` and `4691125P` readbacks have passed. It does not authorize production operation, automatic Lot updates, job upload, printer-state changes, or a print start.

For a communication-only ExternText test, the protocol manual does not require a particular loaded job or an EXTTXT Field 0 object: `=ET` transfers the external-text parameter and `?ET` inquires it. The separate Scriptlanguage manual describes Field 0 as the job-side mechanism that inserts this variable into printed text; that is a print-job integration requirement, not a prerequisite for protocol transport/readback. As a commissioning safety policy, keep printing stopped, prevent print triggers, and use one ExternText writer for any first physical write. The application cannot independently check these conditions; its current confirmation asks the operator to attest to them. An earlier app version also required a non-Unicode Field 0 job and matching lengths/offsets before a write; that extra check was unrelated to communication and did not verify job integration. Field 0 integration and physical printing remain separate, untested steps.

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

### Commissioning observations — 2026-11-26

The operator reported that the cable, WAGO link, server/printer addressing, printer subnet and port, ping, and `Test-NetConnection` checks listed in the results table below completed successfully. These site observations are recorded as operator-reported; they were not independently repeated here. The project `.env` was inspected without exposing unrelated settings: `LJ3_IP=172.28.169.248` and `LJ3_PORT=3000`, matching the intended target. The Python application’s option 1 was then run once and displayed `TCP CONNECTION OK` for `172.28.169.248:3000`, followed by disconnection; no Jet3 protocol command was sent.

The operator identified the printer as a LEIBINGER JET3 ECO, machine No. 2, reported it is not currently used for production, and said the current job display shows Lot No. `4691125P`. The operator confirmed that the NIC1 MAC matches this printer and that its display works normally; the previous blank display was caused by the automatic screen saver. For the write test below, the operator explicitly confirmed printing stopped, triggers inhibited, and authorized one communication-only write/readback despite the app's Field 0 prompt. The Lot `4691125P` job was left unchanged.

The server neighbor table showed `172.28.169.248` as `Reachable` on NIC1 with link-layer address `00-05-51-13-0A-74`; a separate `Unreachable` entry existed on interface `Ethernet`. The operator explicitly approved the earlier read-only `?ET` inquiry. On 2026-11-26 the application sent one `?ET` request and received `^0=ET<CR>`. Raw TX was `b'^0?ET\r'` (hex `5E 30 3F 45 54 0D`); raw RX was `b'^0=ET\r'` (hex `5E 30 3D 45 54 0D`). The decoded ExternText value was the empty string. The response was accepted without a communication or protocol error, and the connection closed normally. No retry or write command occurred.

After the operator confirmed printing stopped and triggers inhibited, and explicitly authorized one communication-only write/readback despite the application's stricter Field 0 prompt, the application sent `=ETTEST123` once at `2026-11-26T05:13:30.350+00:00`. TX bytes were `b'^0=ETTEST123\r'` (hex `5E 30 3D 45 54 54 45 53 54 31 32 33 0D`). The application reported `SENT - UNVERIFIED`; there is no ordinary write acknowledgement. It then sent one `?ET` readback at `2026-11-26T05:13:30.352+00:00`, TX bytes `b'^0?ET\r'` (hex `5E 30 3F 45 54 0D`). No response bytes were received before the peer closed the connection. RX: none (no raw bytes/hex); decoded value: unavailable. The application reported `COMMUNICATION ERROR: Peer closed before a complete =ET reply; readback unavailable.` Verification was **not successful / inconclusive**, not `MISMATCH`, because no value was returned. No retry was made. No printer setting, print state, or job was changed by this test; no printing was started.

On 2026-11-26 a later diagnostic application option 1 TCP-only check connected to `172.28.169.248:3000` at `05:16:34.673+00:00` and disconnected at `05:16:34.675+00:00`; it sent no protocol data. A single option 2 read followed at `05:17:10.222+00:00`: TX `b'^0?ET\r'` (hex `5E 30 3F 45 54 0D`). No RX bytes were received (no raw RX/hex), so no value could be decoded or compared with `TEST123`. At `05:17:13.223+00:00` the application reported `Operation timed out; printer acceptance is unknown. No automatic retry.` It closed the connection. The current readback therefore remains **COMMUNICATION ERROR / NOT VERIFIED**; `TEST123` was not resent.

## Communication-failure investigation — 2026-11-26

The initial investigation was source/manual analysis only. After the operator confirmed local printer status and explicitly authorized the read-only diagnostic, a temporary Python socket check sent only `?RS` and `?ET`. No write command, setting change, restart, or print command was sent; the current job was not changed.

### Findings by question

1. **Does the JET3 require one persistent TCP connection?**
   - **Documented:** The Interfaceprotocol manual describes independently framed packets but does not state that TCP must remain open between commands or that one connection is required per transaction. The HyperTerminal manual’s page 8 example shows multiple commands and replies in one open TCP/IP (Winsock) terminal session. This establishes that a persistent session is illustrated/supported; it does not establish that it is mandatory. See [Manual_LJ3_Interfaceprotocol.pdf](../manual/Manual_LJ3_Interfaceprotocol.pdf), p.4, and [its framing extract](manual-extracted/Manual_LJ3_Interfaceprotocol.txt#L91-L125); [ManualHyperterminalLJ3Engl.pdf](../manual/ManualHyperterminalLJ3Engl.pdf), pp.4 and 8, and [page 8 command sequence](manual-extracted/ManualHyperterminalLJ3Engl.txt#L128-L144) (also [page 8 image](manual-extracted/hyperterminal-page-8.png)).
   - **Historical implementation/evidence:** At the time of the initial failures, `LJ3Client.get_external_text()` opened a fresh connection for each read; the earlier pre-write `?ET` succeeded that way, while immediate post-write readback got peer close and a later new-socket inquiry timed out. The later approved diagnostic succeeded with `?RS` then `?ET` on one persistent socket. This demonstrates that one session works, but does not prove a persistent-connection requirement: the manual does not state one.

2. **Does `=ET` need special termination, acknowledgement, handshake, or a processing sequence?**
   - **Documented:** Standard frames start with `^`, use printer address ASCII `0`, and end with CR (`0x0D`); optional LF may follow. The `=ET` entry defines one string parameter up to 256 characters and CR as final identification, with a stated 20–40 ms LJ3 reaction time. The manual’s general section says packets have no direct reply; the inquiry rule says an inquiry receives its corresponding `=XX` response, and `?ET` is listed. There is no documented mandatory per-write acknowledgement or pre-`=ET` handshake. See Interfaceprotocol PDF pp.4, 8, 11; [frame rules](manual-extracted/Manual_LJ3_Interfaceprotocol.txt#L91-L125), [`?ET` inquiry listing/rule](manual-extracted/Manual_LJ3_Interfaceprotocol.txt#L256-L282), and [`=ET` definition](manual-extracted/Manual_LJ3_Interfaceprotocol.txt#L402-L405).
   - **Optional modes, not ordinary prerequisites:** `!EM` enables echo of processable `!` and `=` commands; it is optional and is not a generic acknowledgement. If it was already enabled on this printer, an echo of `=ET` could have been sent on the write socket, which this client closes without reading; there is no evidence here that echo mode was enabled, and a missed echo alone does not explain the later query timeout. `!LN` enables a length header on printer-to-host data; the manual says it does not change host-to-printer receive format. CRC32 is a separate host-initiated per-transmission procedure using checksum/`!OK` behavior. The application does not enable these modes; its parser accepts the documented length-prefixed response. See Interfaceprotocol PDF pp.7 and 25; [optional echo/length behavior](manual-extracted/Manual_LJ3_Interfaceprotocol.txt#L226-L252) and [CRC procedure](manual-extracted/Manual_LJ3_Interfaceprotocol.txt#L1042-L1075).
   - **Application behavior:** `build_command("=ET", "TEST123")` generates `^0=ETTEST123<CR>` and `build_command("?ET")` generates `^0?ET<CR>`. These match documented framing. See [lj3/protocol.py](../lj3/protocol.py#L14-L34).

3. **Can standby, machine/jet status, or printing status affect these commands?**
   - **Documented:** The Interfaceprotocol manual says command definitions apply to a turned-on device; in standby, only `!PO`, `!RM`, or file transfer are handled. Thus standby is a documented reason a normal `?ET`/`=ET` exchange may not be handled. The read-only `?RS` inquiry reports nozzle state, machine state, and error; machine states include Standby, initialization, service/interval, ready, ready for print start, and Printing. See Interfaceprotocol PDF pp.4, 7–8, 18–19; [standby applicability](manual-extracted/Manual_LJ3_Interfaceprotocol.txt#L123-L125), [`?RS` inquiry](manual-extracted/Manual_LJ3_Interfaceprotocol.txt#L256-L282), and [`=RS` state fields/values](manual-extracted/Manual_LJ3_Interfaceprotocol.txt#L775-L802).
   - **Not documented:** The manual does not state that `=ET` or `?ET` requires printing stopped, nor does it define a printing-state-specific `?ET` failure. The separate Scriptlanguage manual’s double-print check describes consequences when new text is absent after PrintGo; that is job/printing behavior, not a TCP response rule. See [EXTTXT job semantics](manual-extracted/Manual_LJ3_Scriptlanguage.txt#L922-L961).
   - **Live result:** Before the network test, the operator reported the normal main screen, ink jet ON, printhead cover closed, ink 44% and solvent 50% (both OK), 0 pieces/minute, no visible error, and no visible Standby/Initialization message; the exact machine-state code was not shown on the HMI. The subsequent `?RS` response decoded to machine state 4 (Ready for Action), nozzle state 4 (closed), and error 0 (no error). This rules out Standby/Initialization and a reported error for that response, though the response included one extra undocumented numeric field (details below).

4. **Do the manuals define read-only status inquiries?**
   - Yes. `?RS` is explicitly “Query status of data”; the HyperTerminal manual page 8 gives `^0?RS` and an example `^0=RS 6 …` response. The Interfaceprotocol manual defines `=RS` fields and machine-state/error values. The actual response is recorded below. Other listed inquiries include `?VS` (version), `?JL` (loaded job name), `?EL` (error list), `?EV` (event list), `?EX` (extern states), and `?SM` (mail status). See [Interfaceprotocol inquiry list](manual-extracted/Manual_LJ3_Interfaceprotocol.txt#L256-L282), [status response definition](manual-extracted/Manual_LJ3_Interfaceprotocol.txt#L775-L802), and [HyperTerminal status example](manual-extracted/ManualHyperterminalLJ3Engl.txt#L128-L136).
   - At the time of the initial analysis, the application could not issue `?RS`; its original command allowlist accepted only `?ET` and `=ET`. The subsequent implementation update adds a read-only status menu action and decoder. See the current [command allowlist](../lj3/protocol.py#L28-L37).

5. **Could the client’s socket close cause this?**
   - **Original client behavior during the failures:** `send_command()` closed the socket after `sendall()`; for `=ET` it did not read an acknowledgement. The later implementation reuses the session; see the current [session/client operations](../lj3/client.py#L75-L240).
   - **Assessment:** Closing the write socket immediately after `sendall()` is a plausible factor to test because no application-level delivery acknowledgement is received; the manuals do not specify a required post-write dwell or persistent-session rule. It is not proven to be the cause. The earlier diagnostic `?ET` socket remained open during its full 3-second receive deadline and still got no bytes, so “the client closed the read socket too soon” does not explain that timeout; the later valid response took 3061.884 ms, slightly longer than that deadline. The earlier baseline `?ET` also worked with a fresh connection. Do not infer successful printer processing from `sendall()`; the TCP stack’s acceptance is not a printer acknowledgement.

6. **Does the implementation follow the documented protocol?**
   - For the tested ASCII cases, **yes at the frame/protocol level**: address `0`, command group/name, CR, and `=ET`/`?ET` forms are correct; response parsing accepts CR frames and optional LF and validates `=ET`. See [lj3/protocol.py](../lj3/protocol.py#L14-L145). The current menu logs raw TX/RX and timing; see [event display](../lj3/__main__.py#L9-L16).
   - **Historical transport policy:** the earlier application used one socket per operation, no retries, and a 3-second default. In the later successful persistent-session diagnostic, `?ET` took 3061.884 ms from send start through complete CR frame, slightly exceeding that old default. The current application uses a 10-second default. The earlier peer-close remains unexplained; the successful session does not prove persistent TCP is mandatory.

### Read-only diagnostic performed

The operator confirmed the local HMI status before testing: normal main screen; ink jet ON; cover closed; ink 44% and solvent 50% (both OK); 0 pieces/minute; no visible error or Standby/Initialization message; Lot `4691125P`; no current job changes authorized. The exact machine-state code is not available on that screen.

A temporary Python socket diagnostic used a 10-second receive timeout and made no source-file changes. A first pass started at `2026-11-26T05:26:33.559372Z`, opened TCP, and received a complete status frame; response time from the first `recv()` to the CR frame was 62.317 ms (the timer began after `sendall()`). The diagnostic decoder incorrectly required exactly five numeric values. Raw RX was `b'^0=RS4\t4\t0\t0\t230\t1\r'` (hex `5E 30 3D 52 53 34 09 34 09 30 09 30 09 32 33 30 09 31 0D`); the frame was complete, but the local decoder stopped before sending `?ET`. This was a diagnostic-decoder validation error, not a printer-reported error. No retry occurred automatically.

To complete the already authorized sequence after correcting that decoder assumption, one deliberate follow-up diagnostic started at `2026-11-26T05:27:11.563128Z`, opened a new connection, sent one `?RS`, and—on that same connection—sent one `?ET` after decoding the documented fields. The `?RS` request was `b'^0?RS\r'` (hex `5E 30 3F 52 53 0D`). Response time from send start to complete CR frame was 51.037 ms. Raw RX was `b'^0=RS4\t4\t0\t0\t230\t0\r'` (hex `5E 30 3D 52 53 34 09 34 09 30 09 30 09 32 33 30 09 30 0D`).

The Interfaceprotocol manual specifies five `=RS` parameters in order: nozzle state, machine state, error, headcover, and ActSpeed. The first five numeric values therefore decode as nozzle `4` (is closed), machine `4` (Ready for Action), error `0` (no error), headcover `0` (closed), and ActSpeed `230` m/min. The response contains a sixth trailing numeric value (`0`) not defined in the supplied manual; its meaning is intentionally not inferred. The known machine state and error were appropriate for the authorized read-only `?ET` step. Manual field definitions: [=RS parameter definitions](manual-extracted/Manual_LJ3_Interfaceprotocol.txt#L774-L802); [five-value example and optional length framing](manual-extracted/Manual_LJ3_Interfaceprotocol.txt#L226-L252).

On the same TCP connection, TX was `b'^0?ET\r'` (hex `5E 30 3F 45 54 0D`). Response time from send start to complete CR frame was 3061.884 ms. Raw RX was `b'^0=ETTEST123\r'` (hex `5E 30 3D 45 54 54 45 53 54 31 32 33 0D`). The decoded ExternText was `TEST123`; exact comparison: **MATCH**. The socket context closed the connection after the reads. No write command, restart, print command, setting change, or job change occurred. No automatic retry was made.

**Current communication conclusion:** the prior `=ETTEST123` write is now confirmed by a subsequent readback; it was not resent. The successful `?RS` followed by `?ET` on one persistent connection demonstrates that this session handled both inquiries. The `?ET` response exceeded the earlier application's default 3-second timeout by about 62 ms, a concrete timeout concern for the earlier no-data result; the current application uses a 10-second default. The earlier peer-close result remains unexplained; neither result proves that persistent TCP is mandatory. The extra `=RS` field remains undocumented and should be confirmed with Leibinger/vendor documentation if its meaning matters.

### Application update after successful physical communication test

Following the successful exact `TEST123` readback, the application was updated offline to use a 10-second default timeout, reuse a TCP session for sequential menu actions, expose the read-only `?RS` status inquiry, preserve any additional `=RS` parameters as opaque values, and perform action 4 readback only on the same live session as the latest write. It records TX/RX bytes and response/send elapsed time and displays exact text using escaped `repr` formatting. It does not retry writes. Because manual `!EM` mode can echo `=ET` commands and could be confused with a subsequent `?ET` response, the write prompt requires confirmation that echo is disabled; the application does not change or detect that mode. The write-safety prompt now covers stopped production, inhibited print triggers, and absence of another ExternText writer. Field 0 and offset/length checks are not prerequisites for communication-only writes. These code changes do not revise historical test logs or imply additional printer contact. The updated 69-test offline suite uses fake sockets and localhost only.

### Updated application read-only validation (2026-11-26)

The updated application was run against `172.28.169.248:3000` with its displayed
10-second timeout. Menu action 1 reported `TCP CONNECTION OK`; connection
timestamps were `05:48:45.150Z` to `05:48:45.155Z`. This was a TCP handshake
only and sent no LJ3 command. Actions 7 (`?RS`) and 2 (`?ET`) then ran on the
same open application session. The application was exited normally afterward.

**Action 7 — read-only status:** TX was `b'^0?RS\r'` (hex
`5E 30 3F 52 53 0D`). RX was `b'^0=RS4\t4\t0\t0\t230\t0\r'` (hex
`5E 30 3D 52 53 34 09 34 09 30 09 30 09 32 33 30 09 30 0D`). The application
reported a 47.000 ms response time. Decoded documented fields: nozzle state 4
(is closed), machine state 4 (Ready for Action), error 0 (no error), headcover
0 (closed), and ActSpeed 230 m/min. The extra trailing field `0` is retained
as opaque data; its meaning is undocumented.

**Action 2 — read-only ExternText:** TX was `b'^0?ET\r'` (hex
`5E 30 3F 45 54 0D`). RX was `b'^0=ETTEST123\r'` (hex
`5E 30 3D 45 54 54 45 53 54 31 32 33 0D`). The application reported a
3063.000 ms response time and displayed `TEST123`. Exact comparison with the
previously verified `TEST123`: **MATCH**. This was an observation/comparison
only, not menu action 4 (which is tied to a write in the same client session).
No `=ET` write, printer setting change, job modification, restart, or print
start occurred. Physical job rendering and print output remain **NOT TESTED**.

### Controlled communication-only Lot write/readback (2026-11-26)

The operator confirmed printing stopped, print triggers inhibited, no competing
ExternText writer, and `!EM` echo disabled. The current print job was left
unchanged. Field 0 integration and physical printing were explicitly out of
scope and remain **NOT TESTED**. The updated application ran with target
`172.28.169.248:3000` and the 10-second timeout. Its menu option 7 sent the
read-only status request before the write on the same TCP session:

- `?RS` TX: `b'^0?RS\r'` (hex `5E 30 3F 52 53 0D`)
- `=RS` RX: `b'^0=RS4\t4\t0\t0\t230\t0\r'` (hex `5E 30 3D 52 53 34 09 34 09 30 09 30 09 32 33 30 09 30 0D`)
- Response time: **31.000 ms**. Decoded: nozzle 4 (closed), machine 4 (Ready
   for Action), error 0, headcover 0 (closed), ActSpeed 230 m/min. The extra
   trailing `0` is opaque and undocumented.

Menu option 5 previewed `4691125P` as `b'^0=ET4691125P\r'` (hex
`5E 30 3D 45 54 34 36 39 31 31 32 35 50 0D`). After the operator's `SEND` and
`ECHO OFF` confirmations, exactly one write was submitted at
`05:58:37.964Z`. TX was `b'^0=ET4691125P\r'` (hex
`5E 30 3D 45 54 34 36 39 31 31 32 35 50 0D`); write-submit timing was
**0.000 ms**. As expected, no ordinary write acknowledgement is specified, so
the application reported **SENT - UNVERIFIED** pending readback.

Menu option 4 then sent `?ET` on the same still-open socket. TX was `b'^0?ET\r'`
(hex `5E 30 3F 45 54 0D`); RX was `b'^0=ET4691125P\r'` (hex
`5E 30 3D 45 54 34 36 39 31 31 32 35 50 0D`). Response time was
**3016.000 ms**. Exact comparison: expected `'4691125P'`, returned
`'4691125P'` — **VERIFIED**. No retry, job modification, settings change,
restart, or print start occurred. The application session was closed normally.
MES/SQL integration and automatic Lot monitoring remain **NOT IMPLEMENTED**;
this validation covers only the manual communication client.

### Suggested Windows checks (operator-run; not performed for this guide)

1. Check the server NIC configuration with `ipconfig` and the route with `route print`.
2. Check physical link indicators and cable seating along the M12-to-RJ45 and WAGO switch path.
3. An optional `ping 172.28.169.248` can help diagnose reachability. A ping timeout alone does not prove the address is unused or that TCP is unavailable; ICMP may be disabled.
4. Check the TCP listener with PowerShell `Test-NetConnection -ComputerName 172.28.169.248 -Port 3000`. A successful `TcpTestSucceeded` confirms a TCP handshake to that address and port, not printer identity, Jet3 protocol support, or readiness.

## 3. Application architecture and startup

The Phase 1 application is a Python 3.11, standard-library-only terminal tool. It supports manually configuring a target, testing TCP, reading ExternText, sending ASCII ExternText, and comparing a readback. It does not implement SQL, automatic Lot monitoring, product/color lookup, printer job upload, print start/stop, or arbitrary raw commands.

- [lj3/config.py](../lj3/config.py): loads and validates the project-local `.env` subset `LJ3_IP`, `LJ3_PORT`, and `LJ3_TIMEOUT_SECONDS`. Defaults are no IP, port 3000, and a 10-second timeout. Valid ports are 1–65535 and timeout is 0.1–60 seconds. Menu changes are session-only.
- [lj3/protocol.py](../lj3/protocol.py): builds allowlisted `=ET`, `?ET`, and `?RS` frames, validates ASCII text, parses incoming frames, and decodes ExternText/status.
- [lj3/client.py](../lj3/client.py): `LJ3Client.connect()` opens/reuses TCP; sequential `send_command()` calls share that session; `get_printer_status()`, `set_external_text()`, `get_external_text()`, and `verify_external_text()` provide the higher-level actions.
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
| **1 — Test TCP Connection** | Calls `connect()`, reports `TCP CONNECTION OK` or `TCP CONNECTION FAILED`, and leaves a successful session open for later actions. | No command payload. | Valid target and route. TCP success does not prove printer identity or Jet3 command support. |
| **2 — Read Current ExternText** | Calls `get_external_text()`, sends `?ET`, and displays the returned value. | No operator text input; terminal displays the current returned value. | Reachable printer and supported/valid response. This is a read operation and does not change ExternText. |
| **3 — Send Test Text (TEST123)** | Previews fixed `TEST123`, asks for write-safety and echo-mode confirmation, and calls `set_external_text()` once. | Type `SEND` after confirming production stopped, triggers inhibited, and no competing ExternText writer; then type `ECHO OFF` only if `!EM` echo is confirmed disabled. | Writes once to the printer. Field 0 is not required for communication-only testing; job integration and printing remain separate, untested. No automatic retry or readback occurs. |
| **4 — Verify Last Sent Text** | Calls `verify_external_text()` to send `?ET` on the same live TCP session that carried the latest write, then compares exact strings. | Displays expected and returned values with `repr`, and `VERIFIED`, `MISMATCH`, or `COMMUNICATION ERROR`. | Requires a successful write on the still-open session. It refuses to reconnect if that session was lost. Does not write or print. |
| **5 — Send Free Text** | Prompts for operator text, previews it, and sends once after write-safety and echo-mode confirmations. | Printable ASCII only; type `SEND` after confirming production stopped, triggers inhibited, and no competing writer, then `ECHO OFF` only if `!EM` echo is confirmed disabled. | This writes to ExternText. Empty text, controls, non-ASCII, and literal backslashes are rejected. Carets are escaped. Field 0 lengths/offsets apply only to a later print-integration test, not this communication test. |
| **6 — Configure Target** | Prompts for printer IPv4, TCP port, and timeout. | Blank input keeps the current value. | Values are validated; configuration is session-only and clears verification history. Does not configure the server NIC. |
| **7 — Read Printer Status** | Sends read-only `?RS` and displays the five manual-defined `=RS` parameters. | No operator text input. Additional response parameters are shown as opaque bytes, with no speculative labels. | Does not modify printer state. Uses/reuses the current session; raw RX and elapsed response time are logged. |
| **0 — Quit** | Exits and closes any local socket. | No further input. | If an operation was interrupted, the printer may have received some or all of a write; there is no automatic retry. |

## 5. JET3 protocol and printer job requirements

### Frame and command behavior

The interface protocol uses `^` + ASCII destination address + command and parameters + final CR. The printer address is ASCII `0` (`0x30`), not binary zero. Optional LF may follow CR; the application sends CR only. A caret in data is escaped as `\^`. Ordinary command packets do not have a guaranteed direct acknowledgement.

- **Write:** `=ET` sets ExternText. The application frame for `TEST123` is `^0=ETTEST123<CR>`; the final byte is CR (`0x0D`).
- **Read:** `?ET` requests ExternText. The expected ordinary response, based on the manual’s general inquiry rule, is `^0=ET<value><CR>`. A five-digit length-prefixed response is also supported by the parser.
- **Verification:** the current application sends the readback on the same live TCP session as the latest write and compares exact strings. Spaces are preserved; they are not stripped or normalized. It refuses to reconnect after that session is lost. The operator must confirm optional `!EM` command echo is disabled; the app neither detects nor changes that mode.
- **No write acknowledgement:** a successful `sendall()` is not proof the Jet3 accepted the value. The application labels the result `SENT - UNVERIFIED`; it does not wait for an undocumented write ACK.

The manual lists `?ET` and the general `?XX` → `=XX` inquiry rule, but gives no dedicated `?ET` response example or minimum firmware version. Therefore, support and actual response format are commissioning checks, not guaranteed by the application.

`LJ3Client.connect()` is the TCP handshake; `send_command()` sends; `_read_external_text_frame()` receives and validates; `set_external_text()` writes; `get_external_text()` reads; and `verify_external_text()` compares. See [lj3/client.py](../lj3/client.py#L69-L83), [lj3/client.py](../lj3/client.py#L95-L201), and [lj3/protocol.py](../lj3/protocol.py#L14-L118).

### Printer-side setup

At the Jet3, distinguish protocol communication checks from job/print integration checks:

1. **Network:** under Settings / Basic settings / IP_Adress, verify IP `172.28.169.248` and the site-approved subnet mask.
2. **Interface:** under Extra / Interface settings / Connection Typ, select Ethernet and confirm port `3000`.
3. **Power/state:** the interface manual says its command definitions apply to a turned-on device; standby handling is limited. The application does not read or enforce machine state.
4. **Communication-only `=ET` / `?ET` test:** the interface manual defines `=ET` as ExternText parameter transfer and `?ET` as an inquiry. It does not state that a loaded job or Field 0 object is required to send/store/read this value. The printer must be turned on (not in standby, according to the manual’s general command applicability). This does not verify that any job uses the value.
5. **Separate job integration:** to verify rendering in a job, a job must contain an object using `{e}` / EXTTXT and **Field Number 0**. Mailing fields 1+ are not the ExternText field. Keep the existing Lot `4691125P` job untouched; any future integration test should use a separately saved copy with a distinct test name, created by an approved local procedure. The supplied manuals do not describe the printer UI’s copy/Save As workflow. Do not proceed to this integration step unless separately authorized.
6. **Text layout for integration only:** EXTTXT object length is 1–100, and character offset is 0–255. The largest offset-plus-placeholder count across objects determines the job’s required input length. For `TEST123`, check that the test object can show all seven characters at the intended offset.
7. **Font for integration only:** use a non-Unicode font for ASCII test output. Unicode fonts require a different hexadecimal representation according to the interface manual; this application blocks non-ASCII input.
8. **Double-print checking for integration:** establish the intended Check double prints setting with the responsible operator. The script manual says missing new external text after PrintGo can stop printing and generate an error when this setting is enabled.
9. **Interface modes:** use normal unpadded output. The client does not configure echo, length mode, CRC, or other printer interface state. It accepts a length header but does not support fixed-block space padding.
10. **Exclusive writer:** ensure no other controller changes ExternText during the test. The protocol provides no transaction IDs or concurrent-writer protection.

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
   **Expected:** `TCP CONNECTION OK`; no Jet3 command is transmitted. In the current application, the successful session stays open for later sequential menu actions. The disconnection recorded above was from the earlier application version.
   **Pass:** exact success is displayed. **Fail:** `TCP CONNECTION FAILED` or an error; record message and stop. TCP success alone does not prove printer identity/readiness.
7. **Verify the responding device’s identity (no protocol command).** Compare the server’s current neighbor-table MAC for `172.28.169.248` on NIC1 (`00-05-51-13-0A-74`, observed above) with the MAC printed on the intended Jet3’s chassis/asset label or an authoritative switch/asset record. Do not use ping or TCP success alone as device identification. Confirm with the responsible operator whether the previously blank printer display has recovered and that the printer is in an appropriate state for a read-only inquiry.
   **Expected:** MAC evidence ties `172.28.169.248` on NIC1 to the intended Jet3, and the operator confirms the display/recovery status.
   **Pass:** the operator confirmed MAC `00-05-51-13-0A-74` matches the intended JET3 and the display is working normally; the operator reported the prior blank display was the automatic screen saver. **Fail/Blocked:** MAC does not match or display/recovery remains uncertain; do not send `?ET`.
8. **Read baseline ExternText (option 2; requires explicit approval).** Only after step 7 passes and the operator explicitly approves the inquiry, select **2 Read Current ExternText** and record the displayed value and terminal TX/RX evidence.
   **Expected:** a valid `=ET` readback is displayed, possibly empty if the printer reports an empty value.  
   **Pass:** a valid response is received and recorded. **Fail/Blocked:** timeout, peer close, or protocol error; do not infer empty text or unsupported firmware solely from timeout.

### B. ExternText communication test — no job integration or printing

The protocol manual defines `=ET` as transfer of the ExternText string and `?ET` as its inquiry; it does not make a loaded job or Field 0 object a communication prerequisite. The separate Scriptlanguage manual requires Field 0 only for using this variable in a job's printed text. Keep this section distinct from job integration below.

The operator explicitly confirmed printing stopped, triggers inhibited, and no competing ExternText writer before the single recorded attempt below. “Not used for production” alone is not confirmation of stopped print state or inhibited triggers. Reconfirm those conditions before any future write. The printer must be turned on rather than in standby for normal interface commands.

At the time of the recorded communication test, the application had an additional Phase 1 operator assertion: its startup text said a test job was prepared, its send prompt asked the operator to confirm a non-Unicode Field 0 job, and `set_external_text()` required `stopped_ascii_job_confirmed=True`. This was application policy, not a protocol prerequisite, and the application did not inspect the job or machine state. For that one communication-only attempt, the operator explicitly authorized proceeding despite the stricter prompt, without changing the existing Lot job. This one-time authorization is not evidence that a Field 0 job was loaded and does not verify job integration. The application was subsequently updated as described below; the dated results above remain the original evidence.

9. **Confirm communication-test safety gate.** The operator confirmed printing stopped, PrintGo/other triggers prevented, normal display, and no competing ExternText writer for the recorded test. Do not start/stop printing or change settings as part of this test. Reconfirm before any future write.
10. **Send one `TEST123` write (option 3).** Completed once on 2026-11-26 after explicit operator authorization despite the app prompt. The Lot job was not modified. The application previewed the target/frame and reported `SENT - UNVERIFIED` after `sendall()` completed.
   **Result meaning:** one transport submission only, not proof of printer acceptance. No retry.
11. **Read back once (option 4).** Completed once after the write on a fresh connection. The app sent `?ET`, but the peer closed before returning a complete frame. Result: `COMMUNICATION ERROR`; no decoded value and no `VERIFIED` result. No automatic retry. This does **not** establish a mismatch; the printer returned no value.
12. **One approved diagnostic read (option 2).** After a successful TCP-only connection check, one further read was run on 2026-11-26 with the earlier application's configured 3-second timeout. It sent `?ET` once; no response bytes arrived before that deadline. Result: `COMMUNICATION ERROR`; no decoded value or comparison. No retry and no `TEST123` resend.
13. **Approved status/ExternText diagnostic.** Completed read-only on 2026-11-26: `?RS` returned state 4/Ready for Action, then `?ET` on the same connection returned `TEST123`, exact match. No write or print command was sent in this diagnostic. The full raw data and timing are in the investigation section.
14. **Record and stop.** Record actual TX/RX, decoded value, errors, and verification outcome. Leave the existing job, printer settings, and print state unchanged; do not start printing.

### C. Separate job-integration test — not part of communication-only test

15. If separately authorized later, use an approved local procedure to create/load a separately named copy of the current job; never edit or overwrite the original Lot `4691125P` job. The supplied manuals do not document the printer UI's copy/Save As workflow. Add/confirm `{e}` / EXTTXT Field Number 0 in that copy, non-Unicode font, and placeholder/offset suitable for seven characters. Keep printing stopped while preparing it.
16. Job rendering and physical print output remain **NOT TESTED** until separately approved and performed. A communication `VERIFIED` result alone is not evidence that the job uses ExternText or that any physical print is correct.

## 7. Commissioning results record

Untested items remain **NOT TESTED**. Rows 1–4 contain operator-reported network results; application and operator-confirmation results are recorded in rows 5–16. Update an entry only after that step is confirmed; include evidence/source in Notes. Use `PASS`, `FAIL`, or `BLOCKED` only when supported by an observed result.

| Step | Test | Expected Result | Actual Result | Status | Notes |
|---:|---|---|---|---|---|
| 1 | Address reservation, network path, and intended NIC | Site confirms addresses and route | Address/path reported: server `172.28.169.254`, printer `172.28.169.248`, NIC1, WAGO switch | **NOT TESTED** | Reservation confirmation was not included in report; operator-reported details only. |
| 2 | Printer IP/subnet/Ethernet/port inspection | `172.28.169.248`, approved subnet, Ethernet, port `3000` | Printer configured as `172.28.169.248`; mask `255.255.255.0`; port `3000` | **PASS** | Operator-reported physical inspection/configuration. |
| 3 | Physical link, server NIC, and route | Link present; intended route confirmed | M12 D-coded 4-pin male-to-RJ45 connected; WAGO LINK active; server `172.28.169.254` on NIC1; ping 4/4, 0% loss, <1 ms | **PASS** | Operator-reported; route implied by successful ping/TCP checks. |
| 4 | TCP port 3000 test | TCP handshake succeeds | `Test-NetConnection`: `TcpTestSucceeded = True` to `172.28.169.248:3000` | **PASS** | Operator-reported; does not establish device identity. |
| 5 | Application launch/target check | Menu opens without network I/O; target is correct | Menu opened; target displayed `172.28.169.248:3000` | **PASS** | Observed 2026-11-26. `.env` target matches: IP `172.28.169.248`, port `3000`. |
| 6 | Application option 1 TCP check | `TCP CONNECTION OK`; session remains open | `TCP CONNECTION OK`; original app then disconnected | **PASS** | Observed 2026-11-26 with the earlier app version. No Jet3 protocol bytes sent; identity/readiness explicitly unverified by app. |
| 7 | Verify responding device identity and display status | NIC1 MAC matches intended Jet3; display/recovery confirmed | Operator confirmed MAC `00-05-51-13-0A-74` matches the JET3; display working normally; blanking was automatic screen saver | **PASS** | Operator confirmation; read-only inquiry explicitly approved. |
| 8 | Application option 2 baseline ExternText read | Valid `?ET` / `=ET` response recorded | TX `b'^0?ET\r'` / `5E 30 3F 45 54 0D`; RX `b'^0=ET\r'` / `5E 30 3D 45 54 0D`; decoded value: empty string | **PASS** | One read-only request; valid response; no errors or retry. Application output at `2026-11-26T04:59:01Z`. |
| 9 | Communication write safety gate | Printing stopped; triggers prevented; sole ExternText writer; policy exception explicitly authorized | Operator confirmed readiness and authorized one communication-only test despite app Field 0 prompt | **PASS** | User/operator confirmation before test. |
| 10 | Application option 3 write `TEST123` | One `=ET` attempt; `SENT - UNVERIFIED` or error captured; no retry | TX `b'^0=ETTEST123\r'` / `5E 30 3D 45 54 54 45 53 54 31 32 33 0D`; app: `SENT - UNVERIFIED` | **SENT - UNVERIFIED** | One attempt at `2026-11-26T05:13:30.350+00:00`; acceptance is not acknowledged. No job/settings/print-state change. |
| 11 | Application option 4 immediate readback | One `?ET` read; exact `TEST123` → `VERIFIED`; otherwise mismatch/error recorded | TX `b'^0?ET\r'` / `5E 30 3F 45 54 0D`; RX none; decoded value unavailable; peer closed before response | **COMMUNICATION ERROR** | At `2026-11-26T05:13:30.366+00:00`: `Peer closed before a complete =ET reply; readback unavailable.` No retry. Verification inconclusive; not a mismatch. |
| 12 | Diagnostic TCP check + application option 2 read | TCP connects; one `?ET` returns a complete `=ET` frame | Option 1 connected/disconnected successfully. Option 2 TX `b'^0?ET\r'` / `5E 30 3F 45 54 0D`; RX none; no decoded value | **COMMUNICATION ERROR** | TCP connected at `05:16:34.673Z`; inquiry sent `05:17:10.222Z`; timed out at `05:17:13.223Z` (3 s). No retry, no write. At that time `TEST123` remained unverified; see step 13 for later read-only verification. |
| 13 | Temporary Python persistent-session status and ExternText diagnostic | Complete `?RS`; if appropriate, one `?ET` on same connection | `?RS` decoded: nozzle 4 (closed), machine 4 (Ready for Action), error 0; `?ET` returned `TEST123`, exact match. `?ET` response time 3061.884 ms. | **PASS — READBACK MATCH** | Operator confirmed local HMI state before test. One initial decoder validation error stopped before `?ET`; one deliberate follow-up completed the authorized sequence. A sixth `=RS` numeric field is undocumented and was not interpreted. Full raw TX/RX, hex, timings, and decoding are in the investigation section above. No automatic retry or write. |
| 14 | Earlier `TEST123` communication closeout | TX/RX and result recorded; no print or settings/job change | `TEST123` later returned on a persistent session and matched exactly | **PASS — READBACK MATCH** | Earlier application write was not repeated; job integration and physical print output remain untested. |
| 15 | Separate temporary job integration preparation | Separate saved job with Field 0; original Lot `4691125P` unchanged | — | **NOT TESTED** | Not required for protocol communication; printer UI procedure not covered by supplied manuals. |
| 16 | Job rendering/physical output | Separately authorized physical test result | — | **NOT TESTED** | Not part of communication-only test. |
| 17 | Updated application `?RS` before Lot communication write | Read-only status response decoded; session remains open | TX `b'^0?RS\r'`; RX `b'^0=RS4\t4\t0\t0\t230\t0\r'`; 31.000 ms; Ready for Action, no error | **PASS** | Observed 2026-11-26 at 05:58:20Z. Additional trailing `0` is undocumented/opaque. |
| 18 | Lot communication write, option 5 | One `=ET4691125P` attempt; no retries; no job or setting changes | TX `b'^0=ET4691125P\r'`; write-submit time 0.000 ms; `SENT - UNVERIFIED` before readback | **PASS — SENT ONCE** | Operator confirmed stopped printing, triggers inhibited, sole ExternText writer, and echo disabled. Existing job unchanged. |
| 19 | Same-session Lot readback, option 4 | Exact `?ET` match for `4691125P` | TX `b'^0?ET\r'`; RX `b'^0=ET4691125P\r'`; 3016.000 ms; exact match | **PASS — VERIFIED** | Readback used the write's still-open TCP session. No retry. |
| 20 | Communication milestone closeout | Communication evidence recorded; physical/job work remains separate | `TEST123` and `4691125P` communication readbacks passed; current job and printer settings unchanged | **PASS** | Field 0 integration and physical printing **NOT TESTED**; MES/SQL integration **NOT IMPLEMENTED**. |

## 8. Troubleshooting and limitations

| Symptom | Checks and response |
|---|---|
| Network connection failure | Recheck address reservation, server NIC/IP, subnet/route, cable seating, switch link, printer Ethernet setting, and site network controls. A ping failure alone is inconclusive. |
| TCP connection failure | Confirm the displayed target and printer port, route/firewall policy, and printer power/state. Option 1 is only a TCP handshake. No retry is performed automatically. |
| `?ET` timeout or peer close | Preserve terminal output; check printer state, port, and interface configuration. A timeout is not proof that the value is empty or that firmware lacks `?ET`. The failed session closes; a later explicit read may open a new session. Verification of a write will not reconnect after losing the write's session. |
| Protocol error | Preserve raw bytes and hex. Check frame start/address/CR, optional length header, unexpected controls, padding, incomplete or multiple replies, and interface mode. The parser fails closed; do not bypass it. |
| Unexpected printer response | The app logs unmatched frames; it recognizes `=FC` as CRC failure and nonzero error values in `=RS`. Consult the printer display/vendor documentation; do not invent meanings for other frames. |
| ExternText write failure | Delivery may be partial, complete, or unknown. Do not immediately resend. Read back and inspect the printer before deciding whether another write is appropriate. |
| ExternText read failure | Check TCP and printer state, then inspect the raw response. Unsupported `?ET` is one possibility, not a conclusion from a timeout alone. |
| Readback mismatch | Compare exact spaces and text; inspect competing writers, job font, Field 0, offsets, and placeholders. A successful readback does not establish correct physical output. |

Known limitations: no retries, transaction IDs, concurrency protection, automatic production/Lot workflow, SQL, job upload, printer state interlock, or physical print confirmation. Unicode writes are blocked. Fixed-block padded replies are unsupported. `?ET` firmware support, active-print update behavior, job/power-cycle persistence, print cutover timing, and physical output require separate on-site/vendor confirmation.

For the project’s existing procedure and evidence basis, see [README.md](../README.md), [docs/COMMISSIONING.md](COMMISSIONING.md), [docs/PROJECT_CONTEXT.md](PROJECT_CONTEXT.md), and the PDFs/extracts under [manual](../manual) and [docs/manual-extracted](manual-extracted).
