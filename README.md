# GreyhoundMonitor

GreyhoundMonitor is a Python-based greyhound price monitoring system that tracks TAB fixed-odds prices, detects configured price movements, sends Discord alerts, stores historical data in SQLite, and checks race results for alerted runners.

The tracker is designed to run continuously on a Windows PC and monitor eligible Australian greyhound races throughout the day.

## Features

- Automatically discovers today's TAB greyhound meetings and races
- Tracks runner prices from 3 hours before the scheduled race start
- Stores the first observed price as the runner's initial price
- Updates the current price during subsequent checks
- Supports multiple independent price alert rules
- Sends qualifying alerts to Discord
- Prevents duplicate alerts for the same rule and runner
- Stores alert history in SQLite
- Records the exact price at which an alert triggered
- Checks race results for alerted runners
- Records finishing positions for later analysis
- Supports Power BI analysis through the SQLite database
- Sends a StatusCake heartbeat while the tracker is running
- Can generate external downtime alerts if the tracker stops

---

## How It Works

The tracker automatically finds the day's greyhound races and begins monitoring each race when it enters the monitoring window.

```text
3 hours before race
        │
        ▼
Price monitoring begins
        │
        ▼
Runner prices stored in SQLite
        │
        ▼
Alert rules evaluated
        │
        ├── No alert → Continue monitoring
        │
        └── Alert triggered
                │
                ├── Send Discord notification
                │
                └── Store alert in ALERT_HISTORY
                        │
                        ▼
              Race reaches +20 minutes
                        │
                        ▼
                  Check TAB result
                        │
                        ▼
              Store finishing position
```

This makes it possible to analyse whether runners that generated particular price alerts subsequently won or placed.

---

## Current Price Alerts

Alert rules are configured centrally in:

```text
app/alerts.py
```

The current tracker includes multiple independent alert strategies.

### Price Drift Alert

Triggers when a runner:

```text
Initial Price < $5.00
Current Price > $10.00
```

This identifies runners that were initially relatively short in the market but subsequently drifted substantially.

### Price Shortening Alert

Triggers when:

```text
Initial Price > $10.00
Current Price <= $10.00
Price Drop >= $5.00
```

This identifies higher-priced runners that shorten significantly.

### Low Price Alert

Triggers when:

```text
Initial Price >= $5.00
Current Price <= $2.00
```

This identifies runners that were initially $5.00 or greater and subsequently shorten to $2.00 or less.

Alert rules can be added, removed, or modified in `app/alerts.py`.

---

## Price Polling Frequency

Races are checked at different frequencies depending on how close they are to their scheduled start time.

| Time Until Scheduled Start | Polling Frequency |
|---|---:|
| 60–180 minutes | Every 10 minutes |
| 30–60 minutes | Every 5 minutes |
| 10–30 minutes | Every 2 minutes |
| 10 minutes before to 5 minutes after | Every 1 minute |

Price monitoring stops approximately 5 minutes after the scheduled race start.

---

## Discord Notifications

Discord notifications are sent through a Discord webhook.

When an alert triggers, the notification includes information such as:

- Runner name
- Meeting
- Race number
- Box number
- Initial price
- Current price
- Price movement

A startup notification is also sent when GreyhoundMonitor launches successfully.

The Discord webhook URL is stored in the local `.env` file and should never be committed to GitHub.

---

## Race Result Tracking

GreyhoundMonitor can automatically revisit races that generated price alerts.

Result checking begins:

```text
Scheduled race start + 20 minutes
```

Only races containing an alerted runner need to be checked.

When an official TAB result is available, the finishing position is stored against the runner's alert history.

If a result is not yet available, the tracker leaves the result pending and retries later.

This allows analysis such as:

```text
Alert Type
    ↓
Number of Alerts
    ↓
Number of Winners
    ↓
Strike Rate
```

---

## SQLite Database

GreyhoundMonitor stores its data in:

```text
data/greyhound.db
```

The live database is intentionally excluded from Git.

### RUNNERS

The `RUNNERS` table stores information including:

```text
RUNNERID
MEETINGDATE
MEETINGNAME
VENUECODE
RACENUMBER
RACESTART
RUNNERNUMBER
RUNNERNAME
INITIALPRICE
CURRENTPRICE
```

### ALERT_HISTORY

The `ALERT_HISTORY` table records individual alerts and results.

It includes information such as:

```text
RUNNERID
ALERTID
ALERTPRICE
FINISHPOSITION
RESULTCHECKED
SENTAT
```

This separation allows a single runner to trigger multiple independent alert strategies.

---

## Power BI

The SQLite database can be used as a Power BI data source.

This allows analysis of:

- Initial vs current prices
- Alert frequency
- Alert type
- Alert trigger price
- Winning runners
- Strike rate by alert
- Meeting and race performance
- Historical price movements

Because `greyhound.db` is a live local database, it is not included in this GitHub repository.

---

## StatusCake Monitoring

GreyhoundMonitor supports StatusCake Push Monitoring.

While the tracker is running, it periodically sends a heartbeat to StatusCake.

Current heartbeat interval:

```text
Approximately every 5 minutes
```

If the tracker stops sending heartbeats, StatusCake can independently detect the outage and send a notification.

This can detect situations such as:

- Python process crashes
- Tracker window closes
- Computer shuts down
- Internet connectivity is lost
- Main monitoring loop stops progressing

Because StatusCake runs independently of the tracker PC, downtime alerts can still be sent when the GreyhoundMonitor process itself is unavailable.

---

## Project Structure

```text
GreyhoundMonitor/
│
├── app/
│   ├── alerts.py
│   ├── browser_session.py
│   ├── database.py
│   ├── heartbeat.py
│   ├── main.py
│   ├── models.py
│   ├── monitor.py
│   ├── notifications.py
│   ├── race_finder.py
│   ├── result_scraper.py
│   ├── results_monitor.py
│   ├── scraper.py
│   └── tab_api.py
│
├── data/
│   └── greyhound.db
│
├── .env
├── .gitignore
├── GreyhoundTracker.bat
├── LICENSE
└── README.md
```

Some locally generated or private files, including `.env` and the live SQLite database, are intentionally excluded from GitHub.

---

## Requirements

GreyhoundMonitor requires:

- Windows
- Python 3
- Google Chrome / Chromium support through Playwright
- Internet connection
- Discord webhook
- StatusCake account if external heartbeat monitoring is required

Python packages used by the project include:

```text
playwright
requests
python-dotenv
```

SQLite support is provided by Python's standard library.

---

## Installation

Clone the repository:

```powershell
git clone https://github.com/Tropilacc/GreyhoundMonitor.git
```

Move into the project directory:

```powershell
cd GreyhoundMonitor
```

Create a Python virtual environment:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the required packages:

```powershell
pip install playwright requests python-dotenv
```

Install the Playwright browser:

```powershell
playwright install chromium
```

---

## Environment Configuration

Create a file named:

```text
.env
```

in the root of the project.

Add:

```text
DISCORD_WEBHOOK_URL=YOUR_DISCORD_WEBHOOK_URL
STATUSCAKE_PUSH_URL=YOUR_STATUSCAKE_PUSH_URL
```

Do not commit `.env` to Git.

The repository's `.gitignore` is configured to exclude private environment configuration.

---

## Running GreyhoundMonitor

With the virtual environment activated:

```powershell
python .\app\main.py
```

On the original Windows installation, the tracker can also be launched using:

```text
GreyhoundTracker.bat
```

When the tracker starts successfully, the console will display:

```text
Greyhound Price Monitor
=======================

Monitor started.
Press Ctrl + C to stop.
```

A startup notification should also be sent to the configured Discord channel.

---

## Stopping the Tracker

To stop GreyhoundMonitor manually, use:

```text
Ctrl + C
```

If StatusCake Push Monitoring is enabled, stopping the tracker will eventually cause StatusCake to detect that heartbeats have stopped.

Restarting GreyhoundMonitor resumes the heartbeat and allows StatusCake to detect recovery.

---

## Security

Never commit any of the following:

```text
.env
Discord webhook URLs
StatusCake Push URLs
Live database files
Authentication tokens
API keys
```

If a webhook or credential is accidentally published, revoke or regenerate it immediately.

---

## Disclaimer

GreyhoundMonitor is an experimental data-monitoring and analysis project.

It does not guarantee the accuracy, completeness, or availability of racing, pricing, or result data.

Price movements do not predict race outcomes, and alerts generated by this software should not be interpreted as betting or financial advice.

Users are responsible for ensuring that their use of third-party websites, data, and services complies with the applicable terms of service and laws in their jurisdiction.

---

## Licence

This project is licensed under the MIT License.

See `LICENSE` for details.