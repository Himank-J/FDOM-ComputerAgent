#!/usr/bin/env python3
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

def load_fdom(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def node_signature(node):
    # Use a tuple of key fields to identify duplicates (customize as needed)
    return (
        node.get("type"),
        tuple(node.get("crop", [])),
        node.get("text"),
        node.get("icon"),
        node.get("action"),
    )

def analyze_fdom(fdom):
    stats = {}
    states = fdom.get("states", {})
    edges = fdom.get("edges", [])
    stats["total_states"] = len(states)
    stats["total_edges"] = len(edges)
    node_type_counter = Counter()
    node_sig_counter = Counter()
    state_node_counts = {}
    crop_counter = Counter()
    all_nodes = []

    for state_id, state in states.items():
        nodes = state.get("nodes", [])
        state_node_counts[state_id] = len(nodes)
        for node in nodes:
            node_type = node.get("type", "unknown")
            node_type_counter[node_type] += 1
            sig = node_signature(node)
            node_sig_counter[sig] += 1
            crop = tuple(node.get("crop", []))
            crop_counter[crop] += 1
            all_nodes.append(node)

    stats["total_nodes"] = sum(state_node_counts.values())
    stats["node_types"] = node_type_counter.most_common()
    stats["states_with_most_nodes"] = sorted(state_node_counts.items(), key=lambda x: -x[1])[:10]
    stats["duplicate_nodes"] = [(sig, count) for sig, count in node_sig_counter.items() if count > 1]
    stats["duplicate_crops"] = [(crop, count) for crop, count in crop_counter.items() if count > 1]
    stats["avg_nodes_per_state"] = stats["total_nodes"] / stats["total_states"] if stats["total_states"] else 0

    return stats

def print_stats(stats):
    print("=== FDOM Analysis ===")
    print(f"Total states: {stats['total_states']}")
    print(f"Total nodes: {stats['total_nodes']}")
    print(f"Total edges: {stats['total_edges']}")
    print(f"Average nodes per state: {stats['avg_nodes_per_state']:.2f}")
    print("\nTop 10 node types:")
    for t, c in stats["node_types"][:10]:
        print(f"  {t}: {c}")
    print("\nStates with most nodes:")
    for state_id, count in stats["states_with_most_nodes"]:
        print(f"  {state_id}: {count} nodes")
    print(f"\nDuplicate nodes (by signature): {len(stats['duplicate_nodes'])}")
    for sig, count in stats["duplicate_nodes"][:10]:
        print(f"  {sig}: {count} times")
    print(f"\nDuplicate crops (bounding boxes): {len(stats['duplicate_crops'])}")
    for crop, count in stats["duplicate_crops"][:10]:
        print(f"  {crop}: {count} times")

def main():
    parser = argparse.ArgumentParser(description="Analyze FDOM JSON structure for statistics and repetition.")
    parser.add_argument("--fdom", required=True, help="Path to FDOM JSON file")
    args = parser.parse_args()

    fdom = load_fdom(args.fdom)
    stats = analyze_fdom(fdom)
    print_stats(stats)

if __name__ == "__main__":
    main()
