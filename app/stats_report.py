import os
import sqlite3
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import requests
from dotenv import load_dotenv


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

ENV_PATH = (
    PROJECT_ROOT
    / ".env"
)

DB_PATH = (
    PROJECT_ROOT
    / "data"
    / "greyhound.db"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "alerted_results_7d.png"
)


# ============================================================
# REPORT SETTINGS
# ============================================================

REPORT_DAYS = 7


# ============================================================
# RESULT CODES
# ============================================================

DID_NOT_PLACE_POSITION = 99

SCRATCHED_POSITION = 100


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv(
    ENV_PATH,
    override=True
)

DISCORD_STATS_URL = os.getenv(
    "DISCORD_STATS_URL"
)


# ============================================================
# RESULT CLASSIFICATION
#
# FINISHPOSITION:
#
#     NULL / unresolved
#         Excluded from statistics.
#
#     1
#         Win
#
#     2-98
#         Place
#
#     99
#         Did not Place
#
#     100
#         SCR
#
# RESULTCHECKED must also equal 1.
#
# CHART:
#
#     Win
#     Place
#     Did not Place
#     SCR
#
# All four categories are included in the 100% stacked
# chart.
#
# PERFORMANCE RATES:
#
# SCR runners are still excluded from:
#
#     Win %
#     Place %
#     Did not Place %
#     Win or Place %
#
# because a scratched runner did not actually participate.
#
# Tote has no involvement here.
# ============================================================

def classify_result(
    finish_position
):
    if finish_position is None:
        return None

    if finish_position == 1:
        return "Win"

    if (
        finish_position >= 2
        and finish_position < 99
    ):
        return "Place"

    if (
        finish_position
        == DID_NOT_PLACE_POSITION
    ):
        return "Did not Place"

    if (
        finish_position
        == SCRATCHED_POSITION
    ):
        return "SCR"

    return None


# ============================================================
# GET RAW RESULTS FROM DATABASE
# ============================================================

def get_results():
    """
    Return resolved alerted runners from races occurring
    during the rolling last 7 days.

    ALERTID is deliberately not hard-coded.

    Any alert type present in the database during the
    reporting period will automatically appear in the
    statistics report.

    Includes:

        Win
        Place
        Did not Place
        SCR

    Unresolved runners are excluded because:

        RESULTCHECKED must equal 1
        FINISHPOSITION must not be NULL
    """

    conn = sqlite3.connect(
        DB_PATH
    )

    try:
        rows = conn.execute(
            """
            SELECT
                ah.ALERTID,
                ah.FINISHPOSITION
            FROM ALERT_HISTORY ah
            JOIN RUNNERS r
                ON ah.RUNNERID = r.RUNNERID
            WHERE
                ah.RESULTCHECKED = 1
                AND ah.FINISHPOSITION IS NOT NULL
                AND (
                    CASE
                        WHEN r.RACESTART IS NOT NULL
                             AND TRIM(r.RACESTART) <> ''
                        THEN datetime(r.RACESTART)

                        ELSE datetime(r.MEETINGDATE)
                    END
                ) >= datetime(
                    'now',
                    'localtime',
                    ?
                )
                AND (
                    CASE
                        WHEN r.RACESTART IS NOT NULL
                             AND TRIM(r.RACESTART) <> ''
                        THEN datetime(r.RACESTART)

                        ELSE datetime(r.MEETINGDATE)
                    END
                ) <= datetime(
                    'now',
                    'localtime'
                )
            ORDER BY
                ah.ALERTID
            """,
            (
                f"-{REPORT_DAYS} days",
            )
        ).fetchall()

    finally:
        conn.close()

    return rows


# ============================================================
# BUILD PER-ALERT STATISTICS
# ============================================================

def get_stats():
    """
    Build dynamic per-alert statistics.

    Example:

        {
            "extreme_price_move_up": {
                "Win": 2,
                "Place": 8,
                "Did not Place": 20,
                "SCR": 1
            },

            "price_shortening": {
                ...
            }
        }

    The alert list is completely dynamic.
    """

    rows = get_results()

    stats = {}

    for (
        alert_id,
        finish_position
    ) in rows:

        result_type = classify_result(
            finish_position
        )

        if result_type is None:
            continue

        if alert_id not in stats:
            stats[
                alert_id
            ] = {
                "Win": 0,
                "Place": 0,
                "Did not Place": 0,
                "SCR": 0,
            }

        stats[
            alert_id
        ][
            result_type
        ] += 1

    return stats


# ============================================================
# FORMAT ALERT NAME FOR CHART
# ============================================================

def format_alert_name(
    alert_id: str
) -> str:
    """
    Convert:

        extreme_price_move_up

    into:

        Extreme Price
        Move Up

    Long labels are split over multiple lines to make
    the chart easier to read in Discord.
    """

    words = (
        alert_id
        .replace("_", " ")
        .strip()
        .split()
    )

    if not words:
        return alert_id

    lines = []
    current_line = []

    for word in words:

        proposed = (
            " ".join(
                current_line
                + [word]
            )
        )

        if (
            len(proposed) > 18
            and current_line
        ):
            lines.append(
                " ".join(
                    current_line
                )
            )

            current_line = [
                word
            ]

        else:
            current_line.append(
                word
            )

    if current_line:
        lines.append(
            " ".join(
                current_line
            )
        )

    return "\n".join(
        line.title()
        for line in lines
    )


# ============================================================
# CREATE 100% STACKED CHART
# ============================================================

def create_chart(
    stats
):
    """
    Create one dynamic 100% stacked column per ALERTID.

    Categories:

        Did not Place
        Place
        Win
        SCR

    All resolved runners are included in the chart
    denominator.

    Therefore each bar represents:

        100% of resolved alerted runners

    including runners that were scratched.

    The label above each bar:

        Runners - X

    is the total number of resolved alerted runners
    including SCR.
    """

    if not stats:
        return False

    alert_ids = list(
        stats.keys()
    )

    alert_labels = [
        format_alert_name(
            alert_id
        )
        for alert_id in alert_ids
    ]

    wins = []
    places = []
    did_not_place = []
    scratched = []
    resolved_totals = []

    # ========================================================
    # CALCULATE PERCENTAGES
    # ========================================================

    for alert_id in alert_ids:

        alert_stats = stats[
            alert_id
        ]

        win_count = (
            alert_stats[
                "Win"
            ]
        )

        place_count = (
            alert_stats[
                "Place"
            ]
        )

        did_not_place_count = (
            alert_stats[
                "Did not Place"
            ]
        )

        scratched_count = (
            alert_stats[
                "SCR"
            ]
        )

        resolved_total = (
            win_count
            + place_count
            + did_not_place_count
            + scratched_count
        )

        resolved_totals.append(
            resolved_total
        )

        if resolved_total > 0:

            wins.append(
                win_count
                / resolved_total
                * 100
            )

            places.append(
                place_count
                / resolved_total
                * 100
            )

            did_not_place.append(
                did_not_place_count
                / resolved_total
                * 100
            )

            scratched.append(
                scratched_count
                / resolved_total
                * 100
            )

        else:

            wins.append(
                0
            )

            places.append(
                0
            )

            did_not_place.append(
                0
            )

            scratched.append(
                0
            )

    # ========================================================
    # SCALE WIDTH BASED ON NUMBER OF ALERT TYPES
    # ========================================================

    chart_width = max(
        9,
        len(alert_ids) * 2.2
    )

    figure, axis = plt.subplots(
        figsize=(
            chart_width,
            8
        )
    )

    x_positions = np.arange(
        len(alert_ids)
    )

    # ========================================================
    # STACKED BARS
    #
    # Bottom -> top:
    #
    #     Did not Place
    #     Place
    #     Win
    #     SCR
    #
    # Matplotlib chooses colours automatically.
    # ========================================================

    axis.bar(
        x_positions,
        did_not_place,
        label="Did not Place"
    )

    axis.bar(
        x_positions,
        places,
        bottom=did_not_place,
        label="Place"
    )

    win_bottom = (
        np.array(
            did_not_place
        )
        + np.array(
            places
        )
    )

    axis.bar(
        x_positions,
        wins,
        bottom=win_bottom,
        label="Win"
    )

    scratch_bottom = (
        np.array(
            did_not_place
        )
        + np.array(
            places
        )
        + np.array(
            wins
        )
    )

    axis.bar(
        x_positions,
        scratched,
        bottom=scratch_bottom,
        label="SCR"
    )

    # ========================================================
    # PERCENTAGE LABELS INSIDE EACH SEGMENT
    # ========================================================

    for index in range(
        len(alert_ids)
    ):

        segments = [
            (
                did_not_place[index],
                0
            ),
            (
                places[index],
                did_not_place[index]
            ),
            (
                wins[index],
                (
                    did_not_place[index]
                    + places[index]
                )
            ),
            (
                scratched[index],
                (
                    did_not_place[index]
                    + places[index]
                    + wins[index]
                )
            ),
        ]

        for (
            percentage,
            bottom
        ) in segments:

            # Avoid unreadable labels in very small segments.
            if percentage < 4:
                continue

            axis.text(
                index,
                (
                    bottom
                    + percentage / 2
                ),
                f"{percentage:.1f}%",
                ha="center",
                va="center",
                fontsize=10,
                fontweight="bold",
            )

    # ========================================================
    # TOTAL RUNNERS ABOVE EACH BAR
    #
    # Includes SCR.
    # ========================================================

    for (
        index,
        total
    ) in enumerate(
        resolved_totals
    ):

        axis.text(
            index,
            102,
            f"Runners - {total}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    # ========================================================
    # CHART FORMATTING
    # ========================================================

    axis.set_ylim(
        0,
        108
    )

    axis.set_title(
        "Alerted Greyhound Results by Alert "
        f"- Last {REPORT_DAYS} Days"
    )

    axis.set_xticks(
        x_positions
    )

    axis.set_xticklabels(
        alert_labels
    )

    axis.legend(
        loc="upper center",
        bbox_to_anchor=(
            0.5,
            1.10
        ),
        ncol=4,
        frameon=False,
    )

    axis.grid(
        axis="y",
        alpha=0.25
    )

    figure.tight_layout()

    figure.savefig(
        OUTPUT_PATH,
        dpi=180,
        bbox_inches="tight",
    )

    plt.close(
        figure
    )

    return True


# ============================================================
# OVERALL STATISTICS
# ============================================================

def calculate_overall_stats(
    stats
):
    """
    Calculate overall statistics.

    PERFORMANCE TOTAL:

        Win
        + Place
        + Did not Place

    RESOLVED TOTAL:

        Performance Total
        + SCR

    SCR remains excluded from performance-rate
    denominators because scratched runners did not run.
    """

    wins = 0
    places = 0
    did_not_place = 0
    scratched = 0

    for alert_stats in stats.values():

        wins += (
            alert_stats[
                "Win"
            ]
        )

        places += (
            alert_stats[
                "Place"
            ]
        )

        did_not_place += (
            alert_stats[
                "Did not Place"
            ]
        )

        scratched += (
            alert_stats[
                "SCR"
            ]
        )

    performance_total = (
        wins
        + places
        + did_not_place
    )

    resolved_total = (
        performance_total
        + scratched
    )

    return {
        "Win":
            wins,
        "Place":
            places,
        "Did not Place":
            did_not_place,
        "SCR":
            scratched,
        "Performance Total":
            performance_total,
        "Resolved Total":
            resolved_total,
    }


# ============================================================
# SEND REPORT TO DISCORD
# ============================================================

def send_to_discord(
    stats
):
    if not DISCORD_STATS_URL:
        raise RuntimeError(
            "DISCORD_STATS_URL is missing "
            f"from {ENV_PATH}"
        )

    overall = (
        calculate_overall_stats(
            stats
        )
    )

    performance_total = (
        overall[
            "Performance Total"
        ]
    )

    resolved_total = (
        overall[
            "Resolved Total"
        ]
    )

    wins = (
        overall[
            "Win"
        ]
    )

    places = (
        overall[
            "Place"
        ]
    )

    did_not_place = (
        overall[
            "Did not Place"
        ]
    )

    scratched = (
        overall[
            "SCR"
        ]
    )

    # ========================================================
    # PERFORMANCE RATES
    #
    # SCR is deliberately excluded from the denominator.
    # ========================================================

    win_rate = (
        wins
        / performance_total
        * 100
        if performance_total
        else 0
    )

    place_rate = (
        places
        / performance_total
        * 100
        if performance_total
        else 0
    )

    did_not_place_rate = (
        did_not_place
        / performance_total
        * 100
        if performance_total
        else 0
    )

    win_or_place = (
        wins
        + places
    )

    win_or_place_rate = (
        win_or_place
        / performance_total
        * 100
        if performance_total
        else 0
    )

    now = datetime.now()

    # ========================================================
    # BUILD PER-ALERT TEXT SUMMARY
    # ========================================================

    alert_lines = []

    for (
        alert_id,
        alert_stats
    ) in stats.items():

        alert_performance_total = (
            alert_stats[
                "Win"
            ]
            + alert_stats[
                "Place"
            ]
            + alert_stats[
                "Did not Place"
            ]
        )

        alert_scratched = (
            alert_stats[
                "SCR"
            ]
        )

        alert_resolved_total = (
            alert_performance_total
            + alert_scratched
        )

        alert_lines.append(
            f"**{alert_id}** — "
            f"{alert_resolved_total} resolved "
            f"({alert_scratched} SCR)"
        )

    alerts_text = (
        "\n".join(
            alert_lines
        )
    )

    # ========================================================
    # DISCORD MESSAGE
    # ========================================================

    content = (
        f"**🐕 ALERTED DOG RESULTS — "
        f"LAST {REPORT_DAYS} DAYS**\n\n"

        f"Resolved alerted runners: "
        f"**{resolved_total}**\n"

        f"Runners that participated: "
        f"**{performance_total}**\n"

        f"SCR: "
        f"**{scratched}**\n\n"

        f"🏆 Wins: "
        f"**{wins} "
        f"({win_rate:.1f}%)**\n"

        f"🏅 Places: "
        f"**{places} "
        f"({place_rate:.1f}%)**\n"

        f"❌ Did not place: "
        f"**{did_not_place} "
        f"({did_not_place_rate:.1f}%)**\n\n"

        f"Win or Place rate: "
        f"**{win_or_place_rate:.1f}%**\n\n"

        f"**Alerts included:**\n"
        f"{alerts_text}\n\n"

        f"Updated: "
        f"**{now.strftime('%d/%m/%Y %I:%M %p')}**"
    )

    with open(
        OUTPUT_PATH,
        "rb"
    ) as chart:

        response = requests.post(
            DISCORD_STATS_URL,
            data={
                "content":
                    content
            },
            files={
                "file": (
                    "alerted_results_7d.png",
                    chart,
                    "image/png",
                )
            },
            timeout=30,
        )

    response.raise_for_status()


# ============================================================
# MAIN
# ============================================================

def main():
    print(
        f"Generating {REPORT_DAYS}-day "
        f"alerted greyhound statistics..."
    )

    print(
        f"Project root: "
        f"{PROJECT_ROOT}"
    )

    print(
        f"Database: "
        f"{DB_PATH}"
    )

    print(
        f"Environment file: "
        f"{ENV_PATH}"
    )

    print(
        "DISCORD_STATS_URL loaded:",
        bool(
            DISCORD_STATS_URL
        )
    )

    stats = get_stats()

    print()
    print(
        "Stats by alert:"
    )

    if not stats:
        print(
            "  No resolved alerted runners "
            f"found in the last "
            f"{REPORT_DAYS} days."
        )

        return

    # ========================================================
    # PRINT PER-ALERT STATS
    # ========================================================

    for (
        alert_id,
        alert_stats
    ) in stats.items():

        performance_total = (
            alert_stats[
                "Win"
            ]
            + alert_stats[
                "Place"
            ]
            + alert_stats[
                "Did not Place"
            ]
        )

        resolved_total = (
            performance_total
            + alert_stats[
                "SCR"
            ]
        )

        print()
        print(
            f"  {alert_id}"
        )

        print(
            f"    Win: "
            f"{alert_stats['Win']}"
        )

        print(
            f"    Place: "
            f"{alert_stats['Place']}"
        )

        print(
            f"    Did not Place: "
            f"{alert_stats['Did not Place']}"
        )

        print(
            f"    SCR: "
            f"{alert_stats['SCR']}"
        )

        print(
            f"    Participated: "
            f"{performance_total}"
        )

        print(
            f"    Resolved: "
            f"{resolved_total}"
        )

    # ========================================================
    # OVERALL STATS
    # ========================================================

    overall = (
        calculate_overall_stats(
            stats
        )
    )

    print()

    print(
        "Total resolved alerted runners:",
        overall[
            "Resolved Total"
        ]
    )

    print(
        "Total runners that participated:",
        overall[
            "Performance Total"
        ]
    )

    print(
        "Total SCR:",
        overall[
            "SCR"
        ]
    )

    # ========================================================
    # CREATE CHART
    #
    # The chart can still be generated when every resolved
    # runner is SCR because SCR itself is now represented.
    # ========================================================

    if (
        overall[
            "Resolved Total"
        ]
        == 0
    ):
        print()
        print(
            "No resolved alerted runners "
            "are available for the chart."
        )

        return

    print()
    print(
        "Creating 100% stacked chart..."
    )

    chart_created = create_chart(
        stats
    )

    if not chart_created:
        print(
            "Chart could not be created."
        )

        return

    print(
        f"Chart saved to: "
        f"{OUTPUT_PATH}"
    )

    print(
        "Sending report to Discord..."
    )

    send_to_discord(
        stats
    )

    print(
        "Discord stats report "
        "sent successfully."
    )


if __name__ == "__main__":
    main()