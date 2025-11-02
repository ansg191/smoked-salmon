import json
import os
import statistics
import subprocess
from dataclasses import dataclass
from functools import partial

import anyio
import asyncclick as click

from salmon.common import get_audio_files
from salmon.common.files import process_files


@dataclass
class DRResult:
    idx: int
    dr: float
    peak: float
    rms: float
    file: str


async def calculate_dr(path: str) -> list[DRResult]:
    files_li = get_audio_files(path, True)
    results = await _generate_dr(path, files_li)
    return results


def make_dr_table(results: list[DRResult], audio_info):
    SPACER = " " * 4

    rows = [
        [
            f"DR{round(dr.dr)}",
            f"{dr.peak:+.2f} dB",
            f"{dr.rms:+.2f} dB",
            f"{audio_info[dr.file]['duration'] // 60:02d}:{audio_info[dr.file]['duration'] % 60:02d}",
            dr.file,
        ]
        for dr in results
    ]

    headers = ["DR", "Peak", "RMS", "Duration", "File"]
    all_rows = [headers] + rows

    widths = [max(len(row[i]) for row in all_rows) for i in range(len(headers))]

    def fmt_row(row):
        cells = []
        for i, cell in enumerate(row):
            if i in (0, 4):
                cells.append(f"{cell:<{widths[i]}}")
            else:
                cells.append(f"{cell:>{widths[i]}}")
        return SPACER + SPACER.join(cells) + SPACER

    dr_version = _drmeter_version()
    overall = round(_overall_dr(results))
    line = "-" * (sum(widths) + len(SPACER) * (len(widths) + 1))
    table = (
        f"{line}\n"
        f"{fmt_row(headers)}\n"
        f"{line}\n" + "\n".join(fmt_row(r) for r in rows) + f"\n{line}\n"
        f"Official DR value: DR{overall}\n\n"
        f"{dr_version}\n"
    )
    return table


def make_dr_bbcode(results: list[DRResult], audio_info):
    overall = round(_overall_dr(results))
    table = make_dr_table(results, audio_info)
    bbcode = (
        "[img]https://ptpimg.me/18a92o.png[/img]"
        f"[size=1][b] [color=#2E86C1] {overall} [/color] [/b][/size]"
        "[hide= - ][pre]\n"
        f"{table}\n"
        "[/pre][/hide]\n"
    )
    return bbcode


async def _generate_dr(path: str, files_li: list[str]) -> list[DRResult]:
    results: list[DRResult] = await process_files(
        files_li, lambda file, idx: _generate_dr_for_file(path, file, idx), "Calculating DRs"
    )

    click.secho("\nFinished calculating DR scores.", fg="green")
    click.secho(f"Overall DR: DR{round(_overall_dr(results))}")

    results.sort(key=lambda x: x.idx)

    return results


async def _generate_dr_for_file(path: str, filename: str, idx: int) -> DRResult:
    func = partial(
        subprocess.run,
        [
            "drmeter",
            "-q",
            "-o",
            "json",
            os.path.join(path, filename),
        ],
        check=True,
        capture_output=True,
    )
    out = await anyio.to_thread.run_sync(func)

    stdout = out.stdout.decode("utf-8")
    data = json.loads(stdout)[0]

    dr = data["overall_dr_score"]
    peak = data["overall_peak_db"]
    rms = data["overall_rms_db"]

    if peak == 0.0:
        peak = -0.0

    return DRResult(idx=idx + 1, dr=dr, peak=peak, rms=rms, file=filename)


def _overall_dr(results: list[DRResult]) -> float:
    return statistics.mean((dr.dr for dr in results))


def _drmeter_version() -> str:
    out = subprocess.run(["drmeter", "--version"], check=True, capture_output=True)
    return out.stdout.decode("utf-8").strip()
