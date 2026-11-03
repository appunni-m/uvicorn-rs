"""Summarize the frozen adjacent-pair experiment without replacing failed rows.

This is a candidate on/off analysis on one hosted runner, not a stock-Uvicorn
comparison. Ratios and spread remain descriptive; five pairs cannot establish
general performance.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import statistics


METRICS = {
    'requests_per_second': 'higher',
    'p50_ms': 'lower',
    'p95_ms': 'lower',
    'p99_ms': 'lower',
    'server_cpu_microseconds_per_request': 'lower',
    'server_rss_peak_mib': 'lower',
    'client_cpu_microseconds_per_request': 'lower',
    'client_rss_peak_mib': 'lower',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def distribution(values):
    if not values:
        return None
    return {'count': len(values), 'median': statistics.median(values),
            'minimum': min(values), 'maximum': max(values), 'values': values}


def verify_runtime_files(metadata, expected):
    """Join checkout hashes with the separately captured installed Python bytes.

    BenchmarkEvidence records every loaded package .py file in its dependency
    ledger, including the uvicorn replacement namespace. The source snapshot
    only duplicates selected Python files. The non-executable py.typed marker
    remains bound by the clean Git revision and pre-measurement parity receipt;
    it is not a per-sample executable-source observation.
    """
    for phase in ('before', 'after'):
        sources = metadata['identity_' + phase]['source_files']
        package = metadata.get('installed_dependencies_' + phase, {}).get('uvicorn-rs', {})
        for name, digest in expected.items():
            if name in sources:
                assert sources[name] == digest, name
            relative = PurePosixPath(name)
            if name.startswith('python/') and relative.suffix == '.py':
                module, *tail = relative.parts[1:]
                observations = [package.get('files', {}).get(str(PurePosixPath(root).joinpath(*tail)))
                                for root in package.get('package_roots', [])
                                if PurePosixPath(root).name == module]
                assert observations == [digest], name
            elif name not in sources:
                assert name == 'python/uvicorn/py.typed', name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('execution', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plan_path = args.execution.parent / 'plan.json'
    plan = json.loads(plan_path.read_text())
    execution = json.loads(args.execution.read_text())
    assert execution['plan_sha256'] == sha(plan_path)
    assert execution['complete'] is True
    assert len(execution['attempts']) == plan['planned_pairs'] * 2
    groups = {}
    rejected = []
    for index, planned in enumerate(plan['pairs'], 1):
        attempts = execution['attempts'][(index - 1) * 2:index * 2]
        assert [a['variant'] for a in attempts] == planned['variant_order']
        pair_rows = {}
        for attempt in attempts:
            assert attempt['pair'] == index
            assert all(attempt[key] == value for key, value in planned.items())
            report_path = args.execution.parent / attempt['report_file']
            assert report_path.parent.resolve() == args.execution.parent.resolve()
            reasons = []
            row = None
            if attempt['returncode'] != 0:
                reasons.append('nonzero_runner_exit')
            if not report_path.is_file():
                reasons.append('missing_report')
            else:
                assert sha(report_path) == attempt['report_sha256']
                report = json.loads(report_path.read_text())
                meta = report['metadata']
                assert meta['diagnostic_only'] is False
                assert meta['workloads'] == [planned['workload']]
                assert meta['repetitions'] == 1
                assert meta['identity_stable'] is True
                assert meta['dirty_target'] is False
                assert not meta['modified_or_unrecorded_dependencies']
                assert meta['rustc']
                variant = execution['variants'][attempt['variant']]
                assert meta['git_revision'] == variant['git_commit']
                verify_runtime_files(meta, variant['runtime_files'])
                assert meta['duration_seconds'] == plan['duration_seconds']
                assert meta['warmup_seconds'] == plan['warmup_seconds']
                assert meta['seed'] == plan['seed']
                assert len(report['rows']) == 1
                row = report['rows'][0]
                assert row['server'] == 'uvicorn-rs-' + planned['loop']
                assert row['workload'] == planned['workload']
                assert row['concurrency'] == planned['concurrency']
                identity = row.get('measurement_identity', {})
                expected_native = execution['variants'][attempt['variant']]['native_sha256']
                if (identity.get('native_sha256_before') != expected_native
                        or identity.get('native_sha256_after') != expected_native):
                    reasons.append('missing_or_changed_sample_native_identity')
                if not row.get('timing_valid', False):
                    reasons.extend(row.get('timing_invalid_reasons') or ['timing_invalid'])
                if row.get('failures', 1) != 0:
                    reasons.append('request_correctness_failed')
                if pair_rows and meta['python_environment'] != pair_environment:
                    reasons.append('mismatched_python_environment')
                pair_environment = meta['python_environment']
            if reasons:
                rejected.append({'pair': index, 'variant': attempt['variant'],
                                 'report': str(report_path), 'reasons': reasons})
            else:
                pair_rows[attempt['variant']] = row
        key = planned['workload'] + '/' + planned['loop']
        group = groups.setdefault(key, {'planned_pairs': 0, 'valid_pairs': [],
                                        'metrics': {metric: [] for metric in METRICS}})
        group['planned_pairs'] += 1
        if set(pair_rows) != {'fresh', 'reuse'}:
            continue
        group['valid_pairs'].append(index)
        for metric in METRICS:
            fresh, reuse = pair_rows['fresh'].get(metric), pair_rows['reuse'].get(metric)
            if not isinstance(fresh, (int, float)) or not isinstance(reuse, (int, float)) or fresh <= 0:
                continue
            group['metrics'][metric].append({'pair': index, 'fresh': fresh, 'reuse': reuse,
                                             'reuse_over_fresh': reuse / fresh})
    for group in groups.values():
        group['minimum_three_valid_pairs'] = len(group['valid_pairs']) >= 3
        group['metrics'] = {
            metric: {'direction': METRICS[metric],
                     'fresh': distribution([r['fresh'] for r in rows]),
                     'reuse': distribution([r['reuse'] for r in rows]),
                     'paired_reuse_over_fresh': distribution([r['reuse_over_fresh'] for r in rows]),
                     'pairs': rows}
            for metric, rows in group['metrics'].items()
        }
    result = {'schema': 'peer-read-adjacent-pair-analysis@1',
              'scope': 'normal release candidate reuse versus fresh allocations on this recorded hosted runner only',
              'plan_sha256': sha(plan_path), 'execution_sha256': sha(args.execution),
              'analysis_sha256': sha(Path(__file__)),
              'policy': 'Use complete valid adjacent pairs only; keep every failure/noise row. '
                        'Compare paired ratios and raw spread across all four workloads and both loops. '
                        'Do not infer allocation counts, a stock-Uvicorn gain, other systems, '
                        'or statistical confidence from these descriptive summaries.',
              'source_identity_policy': 'Every executable runtime source hash must match the '
                        'checkout snapshot or installed Python dependency ledger before and after '
                        'each sample. The non-executable py.typed marker is bound by the clean '
                        'Git revision and selected parity receipt, not sampled as executable code.',
              'groups': groups, 'rejected_attempts': rejected,
              'retention_decision': 'requires review against the frozen plan; no automatic speed claim'}
    with args.output.open('x') as output:
        output.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'groups': len(groups), 'rejected_attempts': len(rejected),
                      'output': str(args.output)}))


if __name__ == '__main__':
    main()
