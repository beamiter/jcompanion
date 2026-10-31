#!/usr/bin/env python3
"""Audit retained native compaction evidence; does not create presentation proof."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def verify(directory):
    report = json.loads((directory / 'retirement-compaction-report.json').read_text())
    assert report['passed'], report.get('error')
    transitions, recovery = report['transitions'], report['recovery']
    assert len(transitions) == report['native_handoffs'] >= 71
    events = [json.loads(line) for line in (directory / 'relay-events.jsonl').read_text().splitlines()]
    assert [row['index'] for row in events] == list(range(1, len(events) + 1))
    assert not any(row['action'] == 'error' for row in events)
    by_index = {row['index']: row for row in events}
    original = recovery['original_token']
    source = transitions[0]['source']
    previous = None
    clearances = set()
    receipt_ids = {}

    def verify_proof(label, proof):
        event = proof['relay_event']
        assert by_index[event['index']] == event
        assert event['label'] == label and event['kind'] == 'retired'
        assert event['direction'] == 'client' and event['action'] == 'forward'
        assert event['token'] == proof['token']
        # Older reports call this native_serial: in Frost it is the captured
        # host tree frame, whereas the separate native pass identifies feedback.
        serial = event['presentation_serial']
        assert serial > 0 and serial == proof['native_serial']
        log = (directory / (label + '.log')).read_text(errors='replace')
        publications = {tuple(map(int, item)) for item in re.findall(
            r'producer frame published window=(\d+) counter=(\d+) pass=(\d+)', log)}
        accepted = {tuple(map(int, item)) for item in re.findall(
            r'compositor scene receipt accepted counter=(\d+) pass=(\d+)', log)}
        pairs = [tuple(item) for item in proof['matching_window_counter_pass']]
        assert pairs and all(item in publications and item[1:] in accepted for item in pairs)
        if report['frontend'] == 'frost':
            mapping = {tuple(map(int, item)) for item in re.findall(
                r'native host receipt native_pass=(\d+) cleared_frame=(\d+) body_frame=(\d+) accepted=true', log)}
            bridge = {tuple(item) for item in proof['native_pass_to_captured_tree']}
            assert bridge and bridge <= mapping and all(tree == serial and body == 0 for _, tree, body in bridge)
            assert all(native in {row[0] for row in bridge} for _, _, native in pairs)
        else:
            assert all(native == serial for _, _, native in pairs)
        for window, counter, native in pairs:
            identity = (label, window, counter, native)
            assert identity not in clearances, 'one native receipt credited twice'
            clearances.add(identity)
        receipt_ids[event['index']] = [native for _, _, native in pairs]
        return event

    for item in transitions:
        old, new = item['previous_token'], item['current_token']
        assert item['proof']['token'] == old and new['epoch'] > old['epoch']
        assert old['boot_id'] == new['boot_id'] == original['boot_id']
        assert 1 <= item['retained_exact_tokens'] <= 64
        if previous is not None:
            assert previous == old
            assert item['source'] != source and item['target'] != source
        previous = new
        verify_proof(item['source'], item['proof'])
    compacted = recovery['compacted_state']
    assert len(compacted['retired_tokens']) == 64 and original not in compacted['retired_tokens']
    assert original not in json.loads((directory / 'compacted-before-restart.json').read_text())['retired_tokens']
    first = recovery['first_native_proof']['relay_event']
    assert first == transitions[0]['proof']['relay_event']
    hello = recovery['reconnect_hello']
    assert by_index[hello['index']] == hello and hello['label'] == source
    assert hello['kind'] == 'host_accepted' and hello['boot_id'] != original['boot_id']
    initial = next(row for row in events if row.get('label') == source and row.get('kind') == 'host_accepted')
    assert hello['connection'] > initial['connection']
    assert hello['connection_nonce'] != initial['connection_nonce']
    renewed = verify_proof(source, recovery['renewed_native_proof'])
    ack = recovery['generated_ack']
    assert by_index[ack['index']] == ack
    assert hello['index'] < renewed['index'] < ack['index']
    assert ack['kind'] == 'retirement_accepted' and ack['action'] == 'forward'
    assert ack['token'] == renewed['token'] == original
    assert ack['connection'] == renewed['connection'] == hello['connection']
    assert renewed['presentation_serial'] > first['presentation_serial']
    assert min(receipt_ids[renewed['index']]) > max(receipt_ids[first['index']])
    old_acks = [row for row in events if row.get('label') == source
                and row.get('kind') == 'retirement_accepted' and row.get('token') == original]
    assert any(row['action'] == 'drop' and row['index'] < hello['index'] for row in old_acks)
    assert all(row['index'] >= ack['index'] for row in old_acks if row['action'] == 'forward')
    current = recovery['current_body_untouched_by_old_ack']
    recovered = recovery['recovered_token']
    assert current['boot_id'] == recovered['boot_id'] == hello['boot_id']
    assert current['epoch'] > compacted['epoch'] and recovered['epoch'] > current['epoch']
    assert all(recovered[key] == original[key] for key in ['host_id', 'incarnation', 'surface_id', 'companion_id'])
    assert all(window == int(recovery['native_window']) for window, _, _ in recovery['renewed_native_proof']['matching_window_counter_pass'])
    assert report['same_original_gui_host_and_shell'] and report['fresh_close_with_native_retirement']
    assert report['old_ack_preserved_current_newer_body']
    # Retained PNGs are sampled visible-body evidence, not continuous scanout.
    for sample in report['samples']:
        image = directory / sample['screenshot']
        assert hashlib.sha256(image.read_bytes()).hexdigest() == sample['sha256']
        assert len(sample['visible_body_windows']) <= 1
    return dict(passed=True, frontend=report['frontend'], native_handoffs=len(transitions),
                exact_cache=64, receipt_ids_verified=len(clearances), genuine_new_connection_nonce=True,
                host_tree_and_native_pass_domains_checked=True, fresh_native_receipt_after_restart=True,
                sampled_pngs_verified=len(report['samples']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.directory)))
