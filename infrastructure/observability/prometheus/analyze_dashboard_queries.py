#!/usr/bin/env python3
"""
Analyze complex PromQL queries in Grafana dashboards to identify candidates for recording rules.

This script:
1. Scans all dashboard JSON files
2. Extracts PromQL queries (histogram_quantile, aggregations, etc.)
3. Analyzes complexity (aggregations, time ranges, label cardinality)
4. Scores queries by frequency, complexity, and performance impact
5. Recommends top 20 queries for recording rules
6. Generates recording_rules.yml template

Usage:
    python analyze_dashboard_queries.py --dashboard-dir ../grafana/dashboards
    python analyze_dashboard_queries.py --dashboard-dir ../grafana/dashboards --output analysis.json
    python analyze_dashboard_queries.py --generate-rules

Output:
    - Query analysis (JSON)
    - Recommended recording rules (YAML template)
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass, asdict
from collections import Counter


@dataclass
class QueryAnalysis:
    """Analysis of a single PromQL query."""
    query: str
    query_hash: str  # Normalized query (for deduplication)
    dashboards: List[str]  # Which dashboards use this query
    panel_titles: List[str]  # Panel titles using this query
    frequency: int  # How many times used across dashboards
    complexity_score: int  # 0-100 complexity score
    has_histogram_quantile: bool
    has_rate: bool
    has_aggregation: bool
    time_range: str  # e.g., "5m", "1h"
    label_dimensions: int  # Number of labels in aggregation
    estimated_cardinality: str  # "low", "medium", "high"
    recommended_recording: bool
    recording_name: str  # Suggested recording rule name


class DashboardQueryAnalyzer:
    """Analyze PromQL queries from Grafana dashboards."""

    # Complexity scoring weights
    WEIGHT_HISTOGRAM_QUANTILE = 30
    WEIGHT_RATE = 10
    WEIGHT_AGGREGATION = 15
    WEIGHT_MULTIPLE_LABELS = 20
    WEIGHT_LONG_TIME_RANGE = 15
    WEIGHT_NESTED_FUNCTIONS = 10

    def __init__(self, dashboard_dir: Path, verbose: bool = False):
        self.dashboard_dir = dashboard_dir
        self.verbose = verbose
        self.queries: Dict[str, QueryAnalysis] = {}

    def log(self, message: str):
        """Print message if verbose mode enabled."""
        if self.verbose:
            print(f"[DEBUG] {message}")

    def normalize_query(self, query: str) -> str:
        """
        Normalize PromQL query for deduplication.

        Remove whitespace variations, comments, and format consistently.
        """
        # Remove comments
        query = re.sub(r'#.*$', '', query, flags=re.MULTILINE)

        # Normalize whitespace
        query = re.sub(r'\s+', ' ', query)
        query = query.strip()

        return query

    def extract_time_range(self, query: str) -> str:
        """Extract time range from query (e.g., [5m], [1h])."""
        match = re.search(r'\[(\d+[smhd])\]', query)
        return match.group(1) if match else "unknown"

    def count_label_dimensions(self, query: str) -> int:
        """Count number of labels used in aggregations (by clause)."""
        by_matches = re.findall(r'by\s*\(([^)]+)\)', query)

        if not by_matches:
            return 0

        # Count unique labels across all by() clauses
        all_labels = set()
        for match in by_matches:
            labels = [l.strip() for l in match.split(',')]
            all_labels.update(labels)

        return len(all_labels)

    def estimate_cardinality(self, query: str, label_count: int) -> str:
        """
        Estimate cardinality of query result.

        Based on:
        - Number of labels
        - Specific high-cardinality labels (user_id, session_id, etc.)
        - Aggregation type
        """
        # High-cardinality label patterns
        high_card_labels = ['user_id', 'session_id', 'trace_id', 'conversation_id']

        for label in high_card_labels:
            if label in query:
                return "high"

        # Medium cardinality: 3+ labels
        if label_count >= 3:
            return "medium"

        # Low cardinality: 0-2 labels
        return "low"

    def calculate_complexity(self, query: str) -> int:
        """
        Calculate complexity score (0-100).

        Higher score = more complex = better candidate for recording rule.
        """
        score = 0

        # Histogram quantile (expensive operation)
        if 'histogram_quantile' in query:
            score += self.WEIGHT_HISTOGRAM_QUANTILE

        # Rate/irate (time-consuming)
        if re.search(r'\b(rate|irate)\(', query):
            score += self.WEIGHT_RATE

        # Aggregations (sum, avg, max, etc.)
        if re.search(r'\b(sum|avg|max|min|count)\s*(by|without)\s*\(', query):
            score += self.WEIGHT_AGGREGATION

        # Multiple label dimensions
        label_count = self.count_label_dimensions(query)
        if label_count >= 2:
            score += self.WEIGHT_MULTIPLE_LABELS

        # Long time ranges (> 5m)
        time_range = self.extract_time_range(query)
        if re.match(r'\d+[hd]', time_range) or (re.match(r'(\d+)m', time_range) and int(re.match(r'(\d+)m', time_range).group(1)) > 5):
            score += self.WEIGHT_LONG_TIME_RANGE

        # Nested functions (complex expressions)
        nesting_level = query.count('(') - query.count(')')
        if abs(nesting_level) >= 3:
            score += self.WEIGHT_NESTED_FUNCTIONS

        return min(score, 100)  # Cap at 100

    def generate_recording_name(self, query: str) -> str:
        """
        Generate suggested recording rule name following Prometheus conventions.

        Convention: level:metric:operations
        Example: job:http_requests:rate5m
        """
        # Extract metric name
        metric_match = re.search(r'(\w+)_(\w+)(?:_bucket|_total|_seconds)?', query)

        if not metric_match:
            return "custom:query:5m"

        metric_base = metric_match.group(0)

        # Determine aggregation level
        by_match = re.search(r'by\s*\(([^)]+)\)', query)
        level = by_match.group(1).split(',')[0].strip() if by_match else "job"

        # Determine operation
        operations = []
        if 'histogram_quantile' in query:
            percentile_match = re.search(r'histogram_quantile\((0\.\d+)', query)
            if percentile_match:
                p = int(float(percentile_match.group(1)) * 100)
                operations.append(f'p{p}')

        if 'rate' in query:
            time_range = self.extract_time_range(query)
            operations.append(f'rate{time_range}')
        elif 'sum' in query:
            operations.append('sum')

        operation_str = '_'.join(operations) if operations else 'agg'

        # Build name
        metric_short = metric_base.replace('_total', '').replace('_seconds', '').replace('_bucket', '')
        return f"{level}:{metric_short}:{operation_str}"

    def extract_queries_from_dashboard(self, dashboard_path: Path) -> List[Tuple[str, str]]:
        """
        Extract all PromQL queries from a dashboard JSON.

        Returns:
            List of (query, panel_title) tuples
        """
        try:
            with open(dashboard_path, 'r', encoding='utf-8') as f:
                dashboard = json.load(f)
        except Exception as e:
            print(f"ERROR: Failed to load dashboard {dashboard_path.name}: {e}")
            return []

        queries = []

        # Extract from panels
        panels = dashboard.get('panels', [])

        for panel in panels:
            panel_title = panel.get('title', 'Untitled Panel')
            targets = panel.get('targets', [])

            for target in targets:
                expr = target.get('expr', '')

                if expr and isinstance(expr, str):
                    queries.append((expr, panel_title))

        return queries

    def analyze_all_dashboards(self) -> Dict[str, QueryAnalysis]:
        """Analyze all dashboards and extract query patterns."""
        dashboard_files = list(self.dashboard_dir.glob('*.json'))

        self.log(f"Found {len(dashboard_files)} dashboard files")

        query_occurrences = {}  # {query_hash: [(dashboard, panel_title)]}

        for dashboard_path in dashboard_files:
            self.log(f"Processing dashboard: {dashboard_path.name}")

            queries = self.extract_queries_from_dashboard(dashboard_path)

            for query, panel_title in queries:
                normalized = self.normalize_query(query)

                if not normalized:
                    continue

                query_hash = hash(normalized)

                if query_hash not in query_occurrences:
                    query_occurrences[query_hash] = {
                        'query': query,
                        'dashboards': [],
                        'panel_titles': []
                    }

                query_occurrences[query_hash]['dashboards'].append(dashboard_path.name)
                query_occurrences[query_hash]['panel_titles'].append(panel_title)

        # Analyze each unique query
        for query_hash, data in query_occurrences.items():
            query = data['query']

            # Calculate metrics
            frequency = len(data['dashboards'])
            complexity = self.calculate_complexity(query)
            has_histogram = 'histogram_quantile' in query
            has_rate = 'rate' in query or 'irate' in query
            has_agg = bool(re.search(r'\b(sum|avg|max|min|count)\s*(by|without)', query))
            time_range = self.extract_time_range(query)
            label_dims = self.count_label_dimensions(query)
            cardinality = self.estimate_cardinality(query, label_dims)

            # Should we recommend recording rule?
            # Criteria: complexity >= 40 OR frequency >= 3
            recommended = complexity >= 40 or frequency >= 3

            # Generate recording name
            recording_name = self.generate_recording_name(query)

            analysis = QueryAnalysis(
                query=query,
                query_hash=str(query_hash),
                dashboards=data['dashboards'],
                panel_titles=data['panel_titles'],
                frequency=frequency,
                complexity_score=complexity,
                has_histogram_quantile=has_histogram,
                has_rate=has_rate,
                has_aggregation=has_agg,
                time_range=time_range,
                label_dimensions=label_dims,
                estimated_cardinality=cardinality,
                recommended_recording=recommended,
                recording_name=recording_name
            )

            self.queries[str(query_hash)] = analysis

        return self.queries

    def get_top_queries(self, n: int = 20) -> List[QueryAnalysis]:
        """
        Get top N queries recommended for recording rules.

        Sorted by: complexity * frequency (descending)
        """
        recommended = [q for q in self.queries.values() if q.recommended_recording]

        # Score = complexity * log(frequency + 1)
        import math
        scored = [(q, q.complexity_score * math.log(q.frequency + 1)) for q in recommended]
        scored.sort(key=lambda x: x[1], reverse=True)

        return [q for q, score in scored[:n]]

    def print_summary(self):
        """Print analysis summary."""
        print("\n" + "="*80)
        print("DASHBOARD QUERY ANALYSIS SUMMARY")
        print("="*80)

        total_queries = len(self.queries)
        recommended = sum(1 for q in self.queries.values() if q.recommended_recording)

        print(f"\nTotal unique queries: {total_queries}")
        print(f"Recommended for recording rules: {recommended}")

        # Complexity distribution
        complexity_dist = Counter()
        for q in self.queries.values():
            if q.complexity_score >= 70:
                complexity_dist['High (70+)'] += 1
            elif q.complexity_score >= 40:
                complexity_dist['Medium (40-69)'] += 1
            else:
                complexity_dist['Low (0-39)'] += 1

        print(f"\nComplexity distribution:")
        for level, count in complexity_dist.most_common():
            print(f"  {level:20s}: {count:3d} queries")

        # Query type distribution
        histogram_count = sum(1 for q in self.queries.values() if q.has_histogram_quantile)
        rate_count = sum(1 for q in self.queries.values() if q.has_rate)
        agg_count = sum(1 for q in self.queries.values() if q.has_aggregation)

        print(f"\nQuery type distribution:")
        print(f"  histogram_quantile:  {histogram_count:3d} queries")
        print(f"  rate/irate:          {rate_count:3d} queries")
        print(f"  aggregations:        {agg_count:3d} queries")

        print("="*80 + "\n")

    def export_analysis(self, output_path: Path):
        """Export analysis to JSON."""
        data = {
            'total_queries': len(self.queries),
            'recommended_count': sum(1 for q in self.queries.values() if q.recommended_recording),
            'queries': [asdict(q) for q in self.queries.values()]
        }

        output_path.write_text(json.dumps(data, indent=2), encoding='utf-8')
        print(f"[SUCCESS] Exported analysis to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Analyze Grafana dashboard queries for recording rule candidates'
    )
    parser.add_argument(
        '--dashboard-dir',
        type=Path,
        required=True,
        help='Directory containing Grafana dashboard JSON files'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output JSON file for analysis'
    )
    parser.add_argument(
        '--top-n',
        type=int,
        default=20,
        help='Number of top queries to recommend (default: 20)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )

    args = parser.parse_args()

    # Initialize analyzer
    analyzer = DashboardQueryAnalyzer(args.dashboard_dir, verbose=args.verbose)

    # Analyze all dashboards
    print(f"Analyzing dashboards in: {args.dashboard_dir}")
    queries = analyzer.analyze_all_dashboards()

    # Print summary
    analyzer.print_summary()

    # Get top N recommendations
    top_queries = analyzer.get_top_queries(args.top_n)

    print(f"\n{'='*80}")
    print(f"TOP {args.top_n} RECOMMENDED RECORDING RULES")
    print(f"{'='*80}\n")

    for i, query in enumerate(top_queries, 1):
        print(f"{i}. {query.recording_name}")
        print(f"   Complexity: {query.complexity_score}/100")
        print(f"   Frequency: {query.frequency} dashboard(s)")
        print(f"   Dashboards: {', '.join(set(query.dashboards))}")
        print(f"   Query preview: {query.query[:80]}...")
        print()

    # Export analysis if requested
    if args.output:
        analyzer.export_analysis(args.output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
