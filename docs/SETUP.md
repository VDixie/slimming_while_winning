# Setup — Hardware, Space and Dev Environment

> Fill in the `[ ]` placeholders. The PowerShell commands at the bottom collect
> most of the hardware details for you.

## Computer
| Item | Value |
|---|---|
| Machine type | desktop |
| Windows version | Microsoft Windows 11 Pro 10.0.26300 |
| CPU | AMD Ryzen 9 5900X 12-Core Processor, 12, 24 |
| GPU | NVIDIA GeForce RTX 3080, 4293918720 |
| RAM | 127.9 GB |
| WoW graphics preset / typical fps | Medium, ~60 fps |

## Webcam
| Item | Value |
|---|---|
| Model | Logitec Brio 100 |
| Advertised resolution / fps | 1080p / 30 fps |
| Measured fps in my room's lighting | 15 fps in the 14:13 recordings (likely auto-exposure; check with `sww bench`); 30 fps at 1280x720 with MJPG (DirectShow or Media Foundation); only 5 fps at 720p uncompressed (YUY2). Pose lite model: ~11 ms/frame (`sww bench`, 2026-11-02) |
| Connection | USB 3 |
| Mounting position | top of monitor |

## Microphone
| Item | Value |
|---|---|
| Model | headset |
| Background noise | quiet |

## Play space
| Item | Value |
|---|---|
| Seated or standing while playing | standing |
| Distance from camera | ~1.5 m standing |
| Visible in frame | head + torso + hands; hips at the bottom edge; **knees out of frame** (measured from recordings 2026-11-02; shoulders ~320 px wide at 1280x720, i.e. quite close) |
| Lighting | daylight from window / overhead light at night |
| Background | plain wall |

> Seated play limits gestures mostly to upper body and hands.
> "Running in place" may become "pumping arms" when seated.

## Language and voice
| Item | Value |
|---|---|
| Language for voice commands | English |
| Accent / variety | South African |

## Dev environment
| Item | Value |
|---|---|
| Python version | 3.14 (confirmed: MediaPipe 1.2.0 ships a Python-version-independent Windows wheel and lists 3.9–3.14) |
| Package manager | uv (per DECISIONS.md; install with `winget install --id=astral-sh.uv -e`) |
| Editor / IDE | VS Code |
| Git + hosting | GitHub |
| Repo name / path | slimming_while_winning — C:\Users\vixie\projects\claude\slimming_while_winning |
| Run WoW / Battle.net as admin? | no — keep both at the same privilege level as this app |

## Collecting hardware info (PowerShell)
Run in PowerShell and paste the output into the tables above:

```powershell
Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version
Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors
Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM
"{0:N1} GB RAM" -f ((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
Get-PnpDevice -Class Camera, Image -Status OK | Select-Object FriendlyName
Get-PnpDevice -Class AudioEndpoint -Status OK | Select-Object FriendlyName
python --version; uv --version; git --version
```
