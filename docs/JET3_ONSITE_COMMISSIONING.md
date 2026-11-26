# LEIBINGER JET3 On-Site Commissioning Guide

Commissioning results are updated incrementally. Steps that have not been completed remain **NOT TESTED**. Record results only after a step has actually been completed and confirmed. Do not infer printer identity or readiness from a TCP connection alone. In addition to the earlier `TEST1234` HMI/job-field check, the operator confirmed a combined Lot/Thai value displayed correctly and physically printed on paper on 2026-11-26. Print quality and complete physical character verification still need improvement; see the latest result entry below.

## 1. Scope and safety

This guide covers the Phase 1 terminal application and controlled JET3 commissioning. Status inquiries and exact `TEST123`, `4691125P`, and Thai combined-value readbacks are recorded below. The operator has now confirmed the selected Field 0 Thai configuration displayed correctly on the HMI and printed on paper. The result is limited to the tested job/font/text; print quality and complete physical character verification remain open.

For a communication-only ExternText test, the protocol manual does not require a particular loaded job or an EXTTXT Field 0 object: `=ET` transfers the external-text parameter and `?ET` inquires it. The separate Scriptlanguage manual describes Field 0 as the job-side mechanism that inserts this variable into printed text; that is a print-job integration requirement, not a prerequisite for protocol transport/readback. As a commissioning safety policy, keep printing stopped, prevent print triggers, and use one ExternText writer for any first physical write. The application cannot independently check these conditions; its current confirmation asks the operator to attest to them. An earlier app version also required a non-Unicode Field 0 job and matching lengths/offsets before a write; that extra check was unrelated to communication and did not verify job integration. Field 0 integration and physical printing are separate acceptance checks; the later Thai Field 0 result below records the specific combination now tested.

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
start occurred. At this earlier read-only checkpoint, physical job rendering and print output remained **NOT TESTED**; the later Thai Field 0 test is recorded below.

### Controlled communication-only Lot write/readback (2026-11-26)

The operator confirmed printing stopped, print triggers inhibited, no competing
ExternText writer, and `!EM` echo disabled. The current print job was left
unchanged. Field 0 integration and physical printing were explicitly out of
scope for this communication-only test and remained **NOT TESTED** at that
time. The later Thai Field 0 result is recorded below. The updated application ran with target
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
At the time of this physical test, MES/SQL integration and automatic Lot
monitoring were **NOT IMPLEMENTED**. The later SQL audit implementation is
documented in [DB_INTEGRATION.md](DB_INTEGRATION.md); it has not been used for a
physical printer test.

### Suggested Windows checks (operator-run; not performed for this guide)

1. Check the server NIC configuration with `ipconfig` and the route with `route print`.
2. Check physical link indicators and cable seating along the M12-to-RJ45 and WAGO switch path.
3. An optional `ping 172.28.169.248` can help diagnose reachability. A ping timeout alone does not prove the address is unused or that TCP is unavailable; ICMP may be disabled.
4. Check the TCP listener with PowerShell `Test-NetConnection -ComputerName 172.28.169.248 -Port 3000`. A successful `TcpTestSucceeded` confirms a TCP handshake to that address and port, not printer identity, Jet3 protocol support, or readiness.

## 3. Application architecture and startup

The original Phase 1 application was a Python 3.11 manual terminal tool. The current application retains those actions and adds an automatic transaction, read-only status aggregation, optional SQL audit persistence, and local journal recovery. It still does not implement automatic Lot monitoring, product/color lookup, printer job upload, print start/stop, or arbitrary raw commands. No physical printer commands were sent during the later software/database implementation.

- [lj3/config.py](../lj3/config.py): loads and validates the project-local `.env` subset `LJ3_IP`, `LJ3_PORT`, and `LJ3_TIMEOUT_SECONDS`. Defaults are no IP, port 3000, and a 10-second timeout. Valid ports are 1–65535 and timeout is 0.1–60 seconds. Menu changes are session-only.
- [lj3/protocol.py](../lj3/protocol.py): builds allowlisted `=ET`, `?ET`, `?RS`, `?EX`, and `?JL` frames, validates ASCII text, parses incoming frames, and decodes documented status fields.
- [lj3/client.py](../lj3/client.py): `LJ3Client.connect()` opens/reuses TCP; sequential `send_command()` calls share that session; read-only status inquiries and ExternText operations use the same client session.
- [lj3/transaction.py](../lj3/transaction.py): performs preflight, baseline, one write, exact same-session readback, structured outcome, and per-printer lock.
- [lj3/db.py](../lj3/db.py) and [docs/DB_INTEGRATION.md](DB_INTEGRATION.md): SQL persistence, migrations, and local-journal recovery.
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
| **7 — Automatic ExternText Transaction** | Reads `?RS`, `?EX`, `?JL`, baseline `?ET`; blocks unless machine state 4/error 0/PrintGo low; then sends one `=ET` and exact same-session `?ET` verification. | Enter printable ASCII and confirm stopped production, inhibited triggers, no competing external writer, and disabled `!EM` echo. | No automatic retry. Per-printer lock applies only inside this process. Trigger inhibition, production stop, external writers, and echo state cannot all be detected and remain operator-attested/UNKNOWN. |
| **8 — Read Printer Status** | Read-only `?RS`, `?EX`, and `?JL`; displays documented values, opaque extras, and UNKNOWN conditions. | No text input. | Sends no state-changing command; current status snapshot is journaled and persisted to SQL when available. |
| **9 — Database Status** | Inspects SQL Server version, schema objects, and database permissions. | No credential values displayed. | Uses the local `.env` SQL_SERVER exactly. `127.0.0.1:1433` is intentional because the application and SQL Server are on the same physical server. |
| **10 — Recover Local Transaction Log** | Idempotently syncs durable journal records to SQL. | No printer command. | Does not replay writes; uncertain write intents become `WRITE_OUTCOME_UNKNOWN`. |
| **11 — Experimental Thai ISO-8859-11 `=ET` (UNVERIFIED)** | Legacy global Field 0 ExternText hypothesis; writes `=ET`. | Do not use for the new Thai Mailmode Field 1 test; it can replace the existing Field 0 Lot Number. |
| **12 — Experimental Thai Mailmode Field 1 (UNVERIFIED)** | Shows exact `=MR` raw-byte preview; validates expected Field 0, expected job, readiness, and two empty-FIFO samples; submits one record; verifies queue status and unchanged `?ET`; leaves the record staged. | Requires job EXTTXT parameter 3 = 1, explicit acceptance of the unverified single-byte hypothesis, production stopped, triggers inhibited, sole writer, and echo disabled. Never sends `!GO` or `!FF`; no payload/rendering readback. Do not start printing. |
| **0 — Quit** | Exits and closes any local socket. | No further input. | If an operation was interrupted, the printer may have received some or all of a write; there is no automatic retry. |

### Controlled read-only status and SQL logging validation (2026-11-26)

The operator authorized normal `.env` database verification followed by one
Option 8 status snapshot against `172.28.169.248:3000`. SQL configuration was
not overridden and `.env` was not changed. The in-application Option 9 reported
SQL target `127.0.0.1:1433`, database `CB`, SQL Server `15.0.2000.5` (2019),
`inkjet` present, all five expected tables and four views present, and no
missing objects. This confirms localhost is the intended route to the SQL
Server on the same physical server. No credential values were displayed.

The existing application started without network activity and displayed
`172.28.169.248:3000`. Option 8 opened one TCP session and sent only the three
documented read-only inquiries below. The successful socket was closed normally
when the application exited. No `=ET`, Option 7, printer setting/job change, or
print start/stop command was sent.

**`?RS` — printer status.** TX: `b'^0?RS\r'` (hex `5E 30 3F 52 53 0D`),
16.000 ms. RX: `b'^0=RS4\t4\t0\t0\t230\t0\r'` (hex
`5E 30 3D 52 53 34 09 34 09 30 09 30 09 32 33 30 09 30 0D`). Decoded manual
fields: nozzle state **4 (closed)**; machine state **4 (Ready for Action)**;
printer error **0 (no error)**; headcover **0 (closed)**; ActSpeed **230
m/min**. One trailing numeric field, `0`, is not documented in `=RS` and remains
opaque.

**`?EX` — extern states.** TX: `b'^0?EX\r'` (hex `5E 30 3F 45 58 0D`),
62.000 ms. RX: `b'^0=EX230\t0\t236\t0\t0\t0\r'` (hex
`5E 30 3D 45 58 32 33 30 09 30 09 32 33 36 09 30 09 30 09 30 0D`). Persisted
decoded fields: actual speed **230 m/min**; input bitfield **0**; maximum speed
**236 m/min**; encoder direction **0 (backward)**; PrintGo (Par6) **0 (LOW)**.
The fifth positional value is also `0`; the supplied `=EX` table does not
define Par5, so it is unsupported/uninterpreted by the application. No later
reserved values were returned. A low PrintGo sample does **not** establish
that external triggers are inhibited.

**`?JL` — loaded-job inquiry.** TX: `b'^0?JL\r'` (hex
`5E 30 3F 4A 4C 0D`), 47.000 ms. RX: `b'^0=JLFFSDISK\\\\JOBS\\\\CB-LOT-TEST.job\t16630114\t26-11-26 13:26:02\r'`
(hex `5E 30 3D 4A 4C 46 46 53 44 49 53 4B 5C 5C 4A 4F 42 53 5C 5C 43 42 2D 4C 4F 54 2D 54 45 53 54 2E 6A 6F 62 09 31 36 36 33 30 31 31 34 09 32 36 2D 31 31 2D 32 36 20 31 33 3A 32 36 3A 30 32 0D`). The response begins with active job path `FFSDISK\\\\JOBS\\\\CB-LOT-TEST.job`; additional tab-delimited values are `16630114` and `26-11-26 13:26:02`. The application preserves the full response and does not assign meanings to those trailing values.

**Application-derived state:** `Printing: NO` because the documented machine
state is 4, not state 6; `ExternText ready: YES` under the application's
state-4/error-0 rule. This is a point-in-time status result, not proof that
production is stopped. Trigger inhibition remains **UNKNOWN**; the application
cannot query it. The status check reported no printer or protocol error.

**Persistence verification:** the application reported “saved to local journal
and SQL Server.” The local journal contains one `STATUS_ONLY` record for
`172.28.169.248:3000` with 11 captured events. Using the same `.env` settings,
read-only SQL queries confirmed the matching row in `inkjet.PrinterStatus` and
11 corresponding rows in `inkjet.StatusLog` (3 TX, 3 RX, 3 timing, 2
connection-status events). `inkjet.TransactionLog` records `STATUS_ONLY` /
`READ_ONLY_STATUS`. The stored local time is `2026-11-26 14:08:39.141` Bangkok
(UTC+07:00). The raw `?EX` event in `StatusLog` preserves the unsupported fifth
positional value even though the app does not interpret it.

For the earlier ASCII commissioning steps, Field 0 rendering and physical
print output had not yet been tested. The later Thai Field 0 test is recorded
below. Before any future ExternText write or production step, still confirm manually: (1) the
responsible operator has stopped production; (2) external print triggers are
inhibited at the PLC/line (PrintGo LOW is not proof); (3) no other application,
PLC, or controller will write ExternText; (4) `!EM` command echo is disabled if
same-session readback will be used; and (5) the active job shown above is the
intended job and will remain unchanged unless separate job-change approval is
given. Those confirmations were later obtained for the single controlled test
recorded next; they are not blanket authorization for another write.

### Controlled Option 7 ExternText transaction (2026-11-26)

After the user's approval for this specific transaction, the application was
launched with target `172.28.169.248:3000`. Option 9 first confirmed normal
`.env` SQL configuration `127.0.0.1:1433`, database `CB`, SQL Server
`15.0.2000.5`, and the complete `inkjet` schema (five tables/four views). No
host override was used. The user had confirmed this application was the only
ExternText writer. At the Option 7 prompt, the operator confirmed production
was stopped, external triggers were inhibited, and `!EM` command echo was
disabled. The confirmation event was journaled and persisted.

Requested text: **`TEST1234` (8 printable ASCII characters)**. Expected job:
**`CB-LOT-TEST.job`**. The live `?JL` response basename matched the expected job;
its additional tab-separated values were retained without interpretation. All
automatic gates passed: `=RS` machine state 4 (Ready for Action), error 0,
recognized non-printing state, `=EX` PrintGo LOW, and expected job match. No
readiness blocker or protocol/transport error occurred.

**Status gate frames:**

- `?RS` TX `b'^0?RS\r'` (hex `5E 30 3F 52 53 0D`); RX
   `b'^0=RS4\t4\t0\t0\t230\t0\r'` (hex
   `5E 30 3D 52 53 34 09 34 09 30 09 30 09 32 33 30 09 30 0D`); **62.000 ms**.
- `?EX` TX `b'^0?EX\r'` (hex `5E 30 3F 45 58 0D`); RX
   `b'^0=EX230\t0\t236\t0\t1\t0\r'` (hex
   `5E 30 3D 45 58 32 33 30 09 30 09 32 33 36 09 30 09 31 09 30 0D`); **47.000 ms**.
   PrintGo Par6 is the sixth response parameter and was **0 (LOW)**. The
   preceding fifth positional value `1` is not defined by the supplied `=EX`
   parameter table (which lists Par1–Par4 and Par6); it remains unsupported and
   uninterpreted.
- `?JL` TX `b'^0?JL\r'` (hex `5E 30 3F 4A 4C 0D`); RX
   `b'^0=JLFFSDISK\\JOBS\\CB-LOT-TEST.job\t16630114\t26-11-26 13:26:02\r'`
   (hex `5E 30 3D 4A 4C 46 46 53 44 49 53 4B 5C 5C 4A 4F 42 53 5C 5C 43 42 2D 4C 4F 54 2D 54 45 53 54 2E 6A 6F 62 09 31 36 36 33 30 31 31 34 09 32 36 2D 31 31 2D 32 36 20 31 33 3A 32 36 3A 30 32 0D`); **62.000 ms**. Loaded path basename: `CB-LOT-TEST.job`.

**Baseline, one write, and exact readback:**

- Baseline `?ET` TX `b'^0?ET\r'` (hex `5E 30 3F 45 54 0D`); RX
   `b'^0=ET4691126P\r'` (hex `5E 30 3D 45 54 34 36 39 31 31 32 36 50 0D`);
   **3063.000 ms**. Baseline value: `4691126P`.
- Exactly one write: TX `b'^0=ETTEST1234\r'` (hex
   `5E 30 3D 45 54 54 45 53 54 31 32 33 34 0D`); submit timing **15.000 ms**.
   The printer protocol specifies no ordinary write acknowledgement; this event
   alone was reported `SENT - UNVERIFIED`.
- Same-session verification `?ET` TX `b'^0?ET\r'` (hex
   `5E 30 3F 45 54 0D`); RX `b'^0=ETTEST1234\r'` (hex
   `5E 30 3D 45 54 54 45 53 54 31 32 33 34 0D`); **3047.000 ms**.
- Exact comparison: requested `TEST1234`, returned `TEST1234` — **VERIFIED**.
   Transaction ID `b3baa0b8-68b9-41d7-95ce-30c5c2eb583b`; total elapsed
   **6384.644 ms**. No retry or additional test text was sent.

**Persistence verification:** the application reported local journal and SQL
success. Using normal `.env` configuration, read-only SQL queries confirmed the
`VERIFIED`/`SUCCESS` row in `inkjet.TransactionLog`, one matching status row in
`inkjet.PrinterStatus`, **21** transaction events in `inkjet.StatusLog` (6 TX,
5 RX, 6 timing, one safety attestation, and three connection-status events),
and zero `inkjet.ErrorLog` rows. The append-only local journal contains both
the `WRITE_PENDING` intent and final `VERIFIED` record, including status and
raw-frame hex evidence. No SQL, protocol, transport, or readiness failure was
detected.

The operator confirmed stopped production and trigger inhibition for this
single test; `?EX` PrintGo LOW was independently observed but is not itself
proof of trigger inhibition. `!EM` disabled and sole-writer status are operator
confirmations, not machine-verifiable facts. No job or printer setting was
changed, and no printing was started. Physical printing and Field 0 rendering
remain **NOT TESTED**. Do not perform another write without separate approval.

### Visual verification and Thai External Text assessment (2026-11-26)

At **14:20:42**, the operator confirmed that `TEST1234` was correctly rendered
in the External Text field of the active `CB-LOT-TEST` job. **PASS — visual
External Text field verification.** This is an operator-reported display/job
field observation; it is not a physical printed-product test. No additional
printer command was required for this report.

The requested value was exactly `สีเทานก`. The initial assessment correctly
found that Thai support was not established by the supplied manuals or the
reported configuration. That assessment preceded a later, separately
authorized, one-shot ISO-8859-11 hypothesis experiment documented below.

- The Interfaceprotocol manual, page 27, says External Text or Mailing data
   used with a Unicode font defined in the job must be transferred as
   hexadecimal-coded text. Its `Hello World` example is
   `00480065006C006C006F00200057006F0072006C0064`. The manual does not name a
   specific Unicode encoding/byte order in that passage, nor does it provide a
   Thai example, Thai character map, or confirmation that this printer has a
   Thai-capable font installed. Do not infer a production encoding from the
   example alone.
- The Scriptlanguage manual, page 25, says Unicode fonts are identified by a
   leading `~` in the font name. Before the Thai-field job change, the reported
   font was `16x10_SCG` and character set `ISO1_English`; neither established
   Thai glyph coverage. The operator now reports a new `ISOB_Thai` font at
   24x20 and static Thai rendering in the job editor. The font name lacks the
   documented `~` marker, and the supplied manuals do not identify its encoding
   map. Static editor rendering does not prove dynamic Mailmode byte handling.
- The ordinary application paths remain ASCII-only: `encode_external_text`
   accepts printable ASCII and uses ASCII bytes; standard frame parsing and
   readback decoding remain ASCII-based; Options 3, 5, and 7 block non-ASCII
   input before connecting. Option 11 is the prior single ISO-8859-11 `=ET`
   hypothesis and writes the global Field 0 value. New Option 12 is a separate
   `=MR` Mailmode Field 1 hypothesis; neither establishes a supported or
   general Unicode mode.

**Remaining requirement:** the printer/vendor must confirm the selected
font's Thai glyph coverage and authoritative encoding/length rules for this
firmware before relying on Thai text operationally. Any job/font/character-set
change or physical printing test requires separate approval. The successful
byte comparison below verifies transport/readback only; it cannot substitute
for that confirmation or visual/printed-output validation.

### Controlled Thai ISO-8859-11 hypothesis transaction (2026-11-26)

This was one separately authorized experimental transaction, not a production
encoding approval. The operator freshly confirmed production stopped, external
triggers inhibited, this application was the only ExternText writer, and
`!EM` command echo was disabled. The application first confirmed normal `.env`
SQL settings (`127.0.0.1:1433`, database `CB`, SQL Server 2019, all five
expected tables and four views present). No `.env` values were changed.

Option 11 displayed the exact candidate before the operator entered `SEND`:
text `สีเทานก`, seven Unicode characters, ISO-8859-11 payload `CA D5 E0 B7 D2 B9 A1`,
and complete frame `5E 30 3D 45 54 CA D5 E0 B7 D2 B9 A1 0D`. ISO-8859-11 remained
an unverified hypothesis. No UTF-8, alternate encoding, fallback, job/font
change, printer setting change, or print-start command was used.

**Preflight, on the same TCP session:**

- `?RS` TX `5E 30 3F 52 53 0D`; RX `5E 30 3D 52 53 34 09 34 09 30 09 30 09 32 33 30 09 30 0D`.
   Decoded: nozzle 4 (closed), machine 4 (Ready for Action), error 0, headcover
   0 (closed), ActSpeed 230; trailing `0` remains opaque. Response: 62 ms.
- `?EX` TX `5E 30 3F 45 58 0D`; RX `5E 30 3D 45 58 32 33 30 09 30 09 32 33 36 09 30 09 31 09 30 0D`.
   PrintGo Par6 was 0 (LOW); unsupported Par5 value `1` remains uninterpreted.
   Response: 63 ms. Operator trigger-inhibition attestation remains distinct
   from this LOW sample.
- `?JL` TX `5E 30 3F 4A 4C 0D`; RX
   `5E 30 3D 4A 4C 46 46 53 44 49 53 4B 5C 5C 4A 4F 42 53 5C 5C 43 42 2D 4C 4F 54 2D 54 45 53 54 2E 6A 6F 62 09 31 36 36 33 30 31 31 34 09 32 36 2D 31 31 2D 32 36 20 31 33 3A 32 36 3A 30 32 0D`.
   The reported job path basename was `CB-LOT-TEST.job`, matching the required
   job. Response: 47 ms.
- Baseline `?ET` TX `5E 30 3F 45 54 0D`; RX
   `5E 30 3D 45 54 54 45 53 54 31 32 33 34 0D`; decoded baseline `TEST1234`.
   Response: 3062 ms. All automated readiness/job gates passed.

**Single write and raw-byte verification:**

- Exactly one `=ET` TX: `5E 30 3D 45 54 CA D5 E0 B7 D2 B9 A1 0D`
   (`b'^0=ET\\xca\\xd5\\xe0\\xb7\\xd2\\xb9\\xa1\\r'`). Submit time
   was 0 ms; the protocol does not provide an ordinary write acknowledgement.
- Same-session raw `?ET` TX: `5E 30 3F 45 54 0D`; raw RX:
   `5E 30 3D 45 54 CA D5 E0 B7 D2 B9 A1 0D`
   (`b'^0=ET\\xca\\xd5\\xe0\\xb7\\xd2\\xb9\\xa1\\r'`), response 3079 ms.
- Returned payload bytes exactly matched `CA D5 E0 B7 D2 B9 A1`.
   Application result: **VERIFIED / EXPERIMENTAL_ISO8859_11_MATCH**; total
   elapsed time 6401.396 ms. Transaction ID:
   `964dce5a-2c50-4c75-8e3b-20113277e639`.

**Audit verification:** the append-only local journal contains both the
`WRITE_PENDING` intent and final result, with 21 captured events and raw TX/RX
hex. Read-only SQL verification found the matching `VERIFIED` transaction,
one `PrinterStatus` row, 21 `StatusLog` rows including the raw frames, and zero
`ErrorLog` rows. The event audit confirms the exact single experimental
write; there was no retry.

**Interpretation and stop condition:** this establishes only an exact raw-byte
round-trip through `?ET`. It does not show that the JET3 rendered the intended
Thai glyphs in the HMI/job field or printed them. The operator must visually
inspect the displayed External Text value before any further action. No other
text/encoding may be sent without separate authorization. The current job and
printer settings were not changed; printing was not started. Field 0
integration and physical product printing remain **NOT TESTED**.

### Confirmed combined Lot Number and Thai color Field 0 print test (2026-11-26)

The operator confirmed the tested job configuration as `CB-LOT-TEST`, one
External Text Field 0 using character set `ISOB_Thai`, font `24x20`, and
placeholder length `30`. The selected path was the existing `=ET` command with
ISO-8859-11 encoding. Test text: **`4691125P สีเทานกพิราบ`**. The operator
confirmed that TCP communication succeeded, the mixed English/numeric/Thai
value displayed correctly on the HMI, and Thai printing was demonstrated on
paper. Print quality and complete physical character verification still need
improvement; therefore the result is successful for this test but not a claim
of fully accepted print quality.

The existing safety preflight was completed before the one-shot write. The
combined string was transmitted exactly once; no retry was made. Raw evidence:

- `=ET` write TX: `5E 30 3D 45 54 34 36 39 31 31 32 35 50 20 CA D5 E0 B7 D2 B9 A1 BE D4 C3 D2 BA 0D`
- `?ET` verification TX: `5E 30 3F 45 54 0D`
- Raw `?ET` response RX: `5E 30 3D 45 54 34 36 39 31 31 32 35 50 20 CA D5 E0 B7 D2 B9 A1 BE D4 C3 D2 BA 0D`
- Verification: **VERIFIED — raw payload matched exactly**.

No Mailmode, `=MR`, or FIFO operation was needed or used. No application
functionality was changed for this test. The result establishes the
operator-confirmed job/font/Field 0/text combination only; it does not certify
arbitrary Thai content, all glyphs, future jobs, active-production cutover, or
general Unicode behavior. No printer command or print start occurred during
the later documentation and Git operations.

### Offline Mailmode Field 1 implementation review (2026-11-26)

The following protocol statements were checked by extracting the relevant pages
from the supplied original PDFs, not only from the searchable text extracts:

- [Interfaceprotocol PDF, p.16](../manual/Manual_LJ3_Interfaceprotocol.pdf):
   `=MR` takes a string formatted as record number, tab, Field 1, tab, Field 2,
   etc., followed by CR. The record number is required; ordinary sequence
   numbers are consecutive and have no leading zeroes, while record number `0`
   is explicitly an exception. Up to 255 fields are described. A field must not
   contain `^` unless escaped as `\\^`.
- [Scriptlanguage PDF, p.21](../manual/Manual_LJ3_Scriptlanguage.pdf): in the
   `EXTTXT` parameter list, parameter 3 is explicitly “Field number”: `0` is
   ExtText and `1…x` are Mailmode field numbers. This confirms the interpretation
   only if the changed editor property is this exact parameter—not merely an
   unnamed numeric setting. Parameter 5 is Check double prints and is not the
   field selector.
- [Interfaceprotocol PDF, p.20](../manual/Manual_LJ3_Interfaceprotocol.pdf):
   `?SM` returns five values: FIFO depth, entries, last-started print number,
   StopAt number, and whether that last print finished. The manual recommends
   issuing `?SM` twice; the second response is current. It notes entries are
   reduced for a record already removed for printing. The application parser
   retains any extra response parameters as opaque values.
- [Interfaceprotocol PDF, p.26](../manual/Manual_LJ3_Interfaceprotocol.pdf):
   the mailing procedure lists `=MR`, `=CM`, `?SM`, and `!FF`; `!FF` is the
   documented Mail FIFO clear. The same page warns that record `0` bypasses
   sequence checks and the last record can be printed again on later PrintGo
   events when the FIFO is empty. `?SM` reports queue state, not record identity;
   it cannot prove that a sole entry is the test record or exclude a concurrent
   producer between inquiry and clear. For that reason the application does
   not expose or send `!FF`, and the experimental path intentionally leaves a
   staged record. Any cleanup requires separate approval and an independently
   isolated procedure; do not start printing.
- [Interfaceprotocol PDF, p.27](../manual/Manual_LJ3_Interfaceprotocol.pdf):
   Unicode-font ExternText **or Mailing** data must be hexadecimal-coded. The
   example maps “Hello World” to `00480065006C006C006F00200057006F0072006C0064`;
   the passage does not name the encoding or specify the `ISOB_Thai` font.
- [Scriptlanguage PDF, p.25](../manual/Manual_LJ3_Scriptlanguage.pdf): Unicode
   fonts are marked with a leading `~` in their name. The reported `ISOB_Thai`
   name lacks that marker, but this alone does not establish whether the font
   uses ISO-8859-11, TIS-620, Windows-874, or a proprietary byte mapping.
- [Hyperterminal PDF, p.8](../manual/ManualHyperterminalLJ3Engl.pdf): the example
   uses two Mailmode objects with field numbers 1 and 2 and submits a `=MR0`
   record. It demonstrates the distinct mailing path; it does not establish a
   Thai encoding.

**Encoding investigation:** the provided PDFs and repository contain no
`ISOB_Thai` mapping table, font binary, or authoritative crosswalk to
ISO-8859-11, TIS-620, or Windows-874. In the configured Python 3.11 runtime,
all three codecs encode this exact phrase to the same bytes:
`CA D5 E0 B7 D2 B9 A1` (code points
`U+0E2A U+0E35 U+0E40 U+0E17 U+0E32 U+0E19 U+0E01`). That equality means this
phrase cannot distinguish those three encodings; it is not evidence that the
printer font uses any of them. A proprietary mapping also remains possible.
The implementation labels these bytes a single-byte hypothesis, never a
confirmed font encoding. If the selected font is in fact Unicode, the manual's
hex-coded-data rule applies and this raw-byte candidate must not be sent.

**Proposed exact no-print test frame, pending approval:** with the job's
`EXTTXT` parameter 3 verified as `1`, the candidate record is exactly
`^0=MR0<TAB><CA D5 E0 B7 D2 B9 A1><CR>`; raw hex preview:
`5E 30 3D 4D 52 30 09 CA D5 E0 B7 D2 B9 A1 0D`. It contains record number 0,
one tab, and one field value; it contains no `=ET` and therefore does not
write the global Field 0 value. The bytes are an unverified hypothesis for the
reported Thai font. `?SM` is `5E 30 3F 53 4D 0D`; `!FF` is
`5E 30 21 46 46 0D` and is a destructive whole-FIFO clear, not a harmless
inquiry. It is not implemented as an application operation.

The new offline Option 12 workflow is intentionally separate from Option 11.
It requires the operator to confirm the exact job field number and the
single-byte hypothesis, enter the expected current Field 0 value, and attest
production stopped, triggers inhibited, sole-writer status, and disabled echo.
It then reads `?RS`, `?EX`, `?JL`, `?ET`,
and `?SM` twice; it blocks unless the expected job/readiness pass, `?ET` exactly
matches the supplied Lot Number, and both FIFO samples are empty. It journals
intent before one `=MR`, checks `?SM` twice for exactly one entry, and confirms
`?ET` remains unchanged. It then reports `STAGED_UNVERIFIED` and leaves the
record in the FIFO. No print-start or clear command is part of this test.
The count is not a readback of field contents or visual glyph rendering, and
the application provides no way to clear the queue. An actual staged-record
test is not approved by the offline work; do not execute Option 12 until
separate approval is given.

The existing application allowlist did not support `=MR` or `?SM`; offline
changes add a fixed, experimental Field 1 path while retaining normal ASCII
`=ET` unchanged and intentionally do not implement `!FF`. The reported physical job/font changes were not
inspected by this software-only implementation. No printer connection or
command, FIFO read, FIFO clear, or print start occurred during this work. Physical test
execution remains pending your approval; successful queue status would still
not verify Thai rendering or printed output.

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

15. If a separate job-integration test is authorized, use an approved local procedure and do not overwrite unrelated production jobs. The Thai test below used the operator-confirmed existing `CB-LOT-TEST` job and Field 0 configuration; the supplied manuals do not document the printer UI's copy/Save As workflow.
16. The combined Thai Lot/color Field 0 rendering and physical print test is recorded below as completed for the stated sample. Print quality and complete character verification remain **IN PROGRESS**. A communication `VERIFIED` result alone is not evidence of physical correctness; retain the physical-output evidence too.

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
| 20 | Communication milestone closeout | Communication evidence recorded; physical/job work remains separate | `TEST123` and `4691125P` communication readbacks passed; current job and printer settings unchanged | **PASS** | Field 0 integration and physical printing **NOT TESTED**; MES/Lot lookup remains **NOT IMPLEMENTED**. |
| 21 | Normal `.env` SQL connectivity / object inspection | Connect using configured host, database `CB`, and verify `inkjet` objects | Option 9 used `127.0.0.1:1433`; database `CB`; SQL Server `15.0.2000.5`; schema and all 5 tables/4 views present; no missing objects | **PASS** | Observed 2026-11-26. Localhost is intentional because app and SQL Server share the physical server. No host override or credential display. |
| 22 | Authorized Option 8 read-only physical status | Read `?RS`, `?EX`, `?JL`; no writes or state changes | `?RS`: nozzle 4, machine 4, error 0, headcover 0, ActSpeed 230; `?EX`: actual 230, inputs 0, max 236, direction 0, PrintGo LOW; `?JL`: `CB-LOT-TEST.job` response with trailing metadata | **PASS — READ ONLY** | Observed 2026-11-26 07:08:39Z at `172.28.169.248:3000`. Raw frames and opaque fields are recorded in “Controlled read-only status and SQL logging validation.” Printing=NO (derived), readiness=YES; trigger inhibition remains UNKNOWN. |
| 23 | Local and SQL status logging | Persist status snapshot in `inkjet.PrinterStatus` and inquiry evidence in `inkjet.StatusLog` | One local `STATUS_ONLY` record; SQL `PrinterStatus` row confirmed; 11 matching `StatusLog` rows including 3 TX/3 RX/3 timing | **PASS** | Same `.env` configuration and `CB` database; transaction ID `B4D6310F-F37C-49CC-93CB-B8E5D6806C0D`; observed timestamp `2026-11-26 14:08:39.141` Bangkok. |
| 24 | Option 7 TEST1234 transaction | Expected job/readiness; capture baseline; send once; exact same-session readback; persist evidence | Baseline `4691126P`; one `=ETTEST1234`; readback `TEST1234`; `VERIFIED`/`SUCCESS` | **PASS — VERIFIED** | Transaction `b3baa0b8-68b9-41d7-95ce-30c5c2eb583b`; total 6384.644 ms; SQL `PrinterStatus` 1 row, `StatusLog` 21 events, `TransactionLog` success, `ErrorLog` 0; local intent/final records. See full evidence above. No retry; job/settings unchanged; no printing started. |
| 25 | Active job External Text field visual check | Confirm the verified value is rendered in the active job's External Text field | Operator confirmed `TEST1234` visible/correct in `CB-LOT-TEST` at 14:20:42 on 2026-11-26 | **PASS — VISUAL FIELD CHECK** | Operator-reported visual check; not a printed-product/physical marking test. No additional printer command. |
| 26 | Thai `สีเทานก` support assessment | Review font/charset and manual evidence; do not infer encoding or glyph coverage | Initial review found `16x10_SCG` / `ISO1_English` was not established as Thai-capable; manuals require hexadecimal form for Unicode fonts but do not specify Thai encoding or font coverage | **ASSESSMENT COMPLETE — SUPPORT UNVERIFIED** | The initial assessment preceded a separately authorized one-shot hypothesis test. Vendor confirmation of glyph coverage and operational encoding is still required. |
| 27 | Option 11 one-shot ISO-8859-11 hypothesis | Enforce status/job gates; persist intent; send once; capture exact raw `?ET`; no retry | Baseline `TEST1234`; one frame `5E 30 3D 45 54 CA D5 E0 B7 D2 B9 A1 0D`; raw readback matched exactly; SQL/local journal persisted | **PASS — BYTE MATCH ONLY** | Transaction `964dce5a-2c50-4c75-8e3b-20113277e639`; 6401.396 ms; `VERIFIED` / `EXPERIMENTAL_ISO8859_11_MATCH`; 21 SQL `StatusLog` events, one `PrinterStatus`, zero `ErrorLog`. HMI glyph rendering remains unverified; no retry, job/settings change, or print start. |
| 28 | Visual Thai External Text field confirmation | Operator inspects HMI/job field and confirms exact intended Thai rendering | Operator reports static Thai rendered in the job editor after creating the new field | **PASS — STATIC EDITOR ONLY** | Does not confirm runtime Mailmode data mapping or dynamic rendering. No physical product printing. |
| 29 | Offline Option 12 Mailmode implementation and frame tests | Verify original PDF command semantics, exact candidate frame, Field 0 preservation, FIFO checks, and that no FIFO-clear operation is exposed | Original PDFs checked; candidate frame `5E 30 3D 4D 52 30 09 CA D5 E0 B7 D2 B9 A1 0D`; complete offline suite: 104 tests passed | **PASS — OFFLINE ONLY** | No real printer connection/command, FIFO access, `!FF`, or printing during that offline work. Mailmode was not used for the later confirmed Field 0 solution. |
| 30 | Combined Lot Number + Thai color physical print using Field 0 | Existing safety preflight; one ISO-8859-11 `=ET`; same-session raw `?ET` equality; HMI and paper inspection | `4691125P สีเทานกพิราบ`; TX/RX payloads identical; correct mixed text shown on HMI; physical Thai print demonstrated | **PASS — PHYSICAL TEST; QUALITY FOLLOW-UP OPEN** | Operator-confirmed 2026-11-26. Job `CB-LOT-TEST`; one External Text Field 0; `ISOB_Thai`; 24x20; placeholder length 30. Exactly one write. No Mailmode, `=MR`, or FIFO. Print quality and complete character verification need improvement. |

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

Known limitations: no automatic retries, no cross-process/external-writer concurrency exclusion, no automatic production/Lot workflow, no job upload, and no printer-state interlock. One combined Thai Field 0 value was confirmed on the HMI and printed on paper; print quality and complete physical character verification remain open. SQL audit persistence is implemented; see [DB_INTEGRATION.md](DB_INTEGRATION.md). The normal Unicode write path remains blocked. Options 11 and 12 are separate experimental paths and were not used for the selected test; neither is a general Unicode feature. Fixed-block padded replies are unsupported. `?ET` firmware support, active-print update behavior, job/power-cycle persistence, print cutover timing, and results for other Thai text require separate confirmation.

For the project’s existing procedure and evidence basis, see [README.md](../README.md), [docs/COMMISSIONING.md](COMMISSIONING.md), [docs/PROJECT_CONTEXT.md](PROJECT_CONTEXT.md), and the PDFs/extracts under [manual](../manual) and [docs/manual-extracted](manual-extracted).
