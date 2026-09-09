"""Generate a read-only visual preview using documentation IPs, never real submissions."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.ip_location import describe_ip

rows = []
for index, address in enumerate(["113.118.113.77", "47.100.0.1", "127.0.0.1", None], 1):
    rows.append({
        "id": index, "created_at": "2026-09-04T12:00:00", "elapsed_ms": 45000,
        "status": "new", "reward_status": "issued", "is_test": True,
        "participant_id": "mp_demo_" + str(index), "participant_code": "DEMO000" + str(index),
        "display_code": "WJ-DEMO0" + str(index) + "02-525", "prize_name": "M 系列 2 片装",
        "degree_label": "525度", "ip": address, "ip_location": describe_ip(address),
    })
html = (ROOT / "web/admin/index.html").read_text(encoding="utf-8")
setup = """
state.rows=SAMPLE_ROWS;state.dashboardStatus='ready';state.total=state.rows.length;
state.openedStatus='ready';state.questionsStatus='ready';state.summary=summaryFromRows(state.rows);
$('#loginPanel').classList.add('hidden');$('#dashboard').classList.remove('hidden');
applyView(); document.querySelector('#dashboard h1').textContent='IP 归属地展示预览（示例数据）';
document.querySelectorAll('button,input,select').forEach(el=>el.disabled=true);
""".replace("SAMPLE_ROWS", json.dumps(rows, ensure_ascii=False))
# The live application remains unchanged; this file is for visual review only.
html = html.replace("</script>", setup + "\n</script>")
html = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"
(ROOT / "qa/ip-location-preview.html").write_text(html, encoding="utf-8")
