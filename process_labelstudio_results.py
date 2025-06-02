#!/usr/bin/env python3
"""
Process Label Studio review results and filter QA pairs based on quality
"""
import json
from pathlib import Path
import argparse
from collections import Counter

def process_labelstudio_export(export_file, original_qa_file):
    """Process Label Studio export and merge with original QA data"""
    
    # Check if export file exists and is not empty
    if not Path(export_file).exists():
        print(f"Error: Export file not found: {export_file}")
        print("\nTo export from Label Studio:")
        print("1. Go to your project in Label Studio")
        print("2. Click 'Export' button")
        print("3. Choose 'JSON' format")
        print("4. Save the file and run this command again with the correct path")
        exit(1)
    
    if Path(export_file).stat().st_size == 0:
        print(f"Error: Export file is empty: {export_file}")
        print("Make sure you've completed some reviews before exporting.")
        exit(1)
    
    # Read Label Studio export
    try:
        with open(export_file, 'r', encoding='utf-8') as f:
            reviewed_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in export file: {export_file}")
        print(f"JSON Error: {e}")
        print("\nMake sure you exported in JSON format from Label Studio.")
        exit(1)
    
    # Check if original QA file exists
    if not Path(original_qa_file).exists():
        print(f"Error: Original QA file not found: {original_qa_file}")
        print("Make sure you've run 'make qa-pairs' first.")
        exit(1)
    
    # Read original QA pairs
    with open(original_qa_file, 'r', encoding='utf-8') as f:
        original_qa = json.load(f)
    
    # Process each reviewed item
    processed_qa = []
    stats = {
        'total': len(reviewed_data),
        'completed': 0,
        'accuracy': Counter(),
        'relevance': Counter(),
        'quality': Counter(),
        'issues': Counter()
    }
    
    for item in reviewed_data:
        # Get the QA data
        qa_data = item.get('data', {})
        qa_id = int(item.get('id', 0)) - 1  # Convert back to 0-based index
        
        # Get annotations (there might be multiple if multiple reviewers)
        annotations = item.get('annotations', [])
        
        if not annotations:
            print(f"Warning: No annotations for QA pair {qa_id + 1}")
            continue
        
        # Use the most recent annotation
        annotation = annotations[-1]
        result = annotation.get('result', [])
        
        # Extract review data
        review_data = {
            'accuracy': None,
            'relevance': None,
            'quality': None,
            'issues': [],
            'notes': None
        }
        
        for r in result:
            if r['from_name'] == 'accuracy':
                review_data['accuracy'] = r['value']['choices'][0]
            elif r['from_name'] == 'relevance':
                review_data['relevance'] = r['value']['choices'][0]
            elif r['from_name'] == 'quality':
                review_data['quality'] = r['value']['choices'][0]
            elif r['from_name'] == 'issues':
                review_data['issues'] = r['value']['choices']
            elif r['from_name'] == 'notes':
                review_data['notes'] = r['value']['text'][0] if r['value']['text'] else None
        
        # Update statistics
        stats['completed'] += 1
        stats['accuracy'][review_data['accuracy']] += 1
        stats['relevance'][review_data['relevance']] += 1
        stats['quality'][review_data['quality']] += 1
        for issue in review_data['issues']:
            stats['issues'][issue] += 1
        
        # Merge with original QA data
        if qa_id < len(original_qa):
            qa_with_review = original_qa[qa_id].copy()
            qa_with_review['review'] = review_data
            qa_with_review['reviewer_id'] = annotation.get('completed_by', 'unknown')
            qa_with_review['review_date'] = annotation.get('created_at', '')
            processed_qa.append(qa_with_review)
    
    return processed_qa, stats

def filter_qa_by_quality(processed_qa, min_quality='Good'):
    """Filter QA pairs based on quality thresholds"""
    
    quality_levels = {
        'Excellent': 4,
        'Good': 3,
        'Fair': 2,
        'Poor': 1
    }
    
    min_level = quality_levels.get(min_quality, 3)
    
    filtered_qa = []
    rejected_qa = []
    
    for qa in processed_qa:
        review = qa.get('review', {})
        quality = review.get('quality', 'Fair')
        accuracy = review.get('accuracy', 'Partially Accurate')
        
        # Accept if quality is good enough AND accuracy is acceptable
        if (quality_levels.get(quality, 0) >= min_level and 
            accuracy in ['Accurate', 'Partially Accurate']):
            filtered_qa.append(qa)
        else:
            rejected_qa.append(qa)
    
    return filtered_qa, rejected_qa

def create_report(stats, filtered_count, rejected_count, output_file):
    """Create a review summary report"""
    
    report = []
    report.append("# QA Review Summary Report\n")
    report.append(f"## Overview")
    report.append(f"- Total QA pairs: {stats['total']}")
    report.append(f"- Reviewed: {stats['completed']} ({stats['completed']/stats['total']*100:.1f}%)")
    report.append(f"- Accepted: {filtered_count}")
    report.append(f"- Rejected: {rejected_count}\n")
    
    report.append("## Accuracy Distribution")
    for accuracy, count in stats['accuracy'].most_common():
        report.append(f"- {accuracy}: {count} ({count/stats['completed']*100:.1f}%)")
    
    report.append("\n## Relevance Distribution")
    for relevance, count in stats['relevance'].most_common():
        report.append(f"- {relevance}: {count} ({count/stats['completed']*100:.1f}%)")
    
    report.append("\n## Quality Distribution")
    for quality, count in stats['quality'].most_common():
        report.append(f"- {quality}: {count} ({count/stats['completed']*100:.1f}%)")
    
    if stats['issues']:
        report.append("\n## Common Issues")
        for issue, count in stats['issues'].most_common():
            report.append(f"- {issue}: {count}")
    
    with open(output_file, 'w') as f:
        f.write('\n'.join(report))
    
    print('\n'.join(report))

def main():
    parser = argparse.ArgumentParser(description='Process Label Studio review results')
    parser.add_argument('export_file', help='Label Studio JSON export file')
    parser.add_argument('--original-qa', default='data/generated/DE000DDA0NU1.pdf_qa_pairs_with_refs.json',
                        help='Original QA pairs file')
    parser.add_argument('--min-quality', default='Good', choices=['Excellent', 'Good', 'Fair'],
                        help='Minimum quality threshold for filtering')
    parser.add_argument('--output-dir', default='data/reviewed',
                        help='Output directory for filtered results')
    
    args = parser.parse_args()
    
    # Create output directory
    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Process the export
    print(f"Processing Label Studio export: {args.export_file}")
    processed_qa, stats = process_labelstudio_export(args.export_file, args.original_qa)
    
    # Filter by quality
    filtered_qa, rejected_qa = filter_qa_by_quality(processed_qa, args.min_quality)
    
    # Save filtered results
    filtered_file = output_path / "filtered_qa_pairs.json"
    with open(filtered_file, 'w', encoding='utf-8') as f:
        json.dump(filtered_qa, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Saved {len(filtered_qa)} accepted QA pairs to {filtered_file}")
    
    # Save rejected for review
    rejected_file = output_path / "rejected_qa_pairs.json"
    with open(rejected_file, 'w', encoding='utf-8') as f:
        json.dump(rejected_qa, f, indent=2, ensure_ascii=False)
    print(f"📝 Saved {len(rejected_qa)} rejected QA pairs to {rejected_file}")
    
    # Create report
    report_file = output_path / "review_report.md"
    create_report(stats, len(filtered_qa), len(rejected_qa), report_file)
    print(f"\n📊 Report saved to {report_file}")
    
    # Create clean version without review metadata for training
    clean_qa = []
    for qa in filtered_qa:
        clean_qa.append({
            'question': qa['question'],
            'answer': qa['answer']
        })
    
    clean_file = output_path / "clean_qa_pairs.json"
    with open(clean_file, 'w', encoding='utf-8') as f:
        json.dump(clean_qa, f, indent=2, ensure_ascii=False)
    print(f"🎯 Saved clean QA pairs for training to {clean_file}")

if __name__ == "__main__":
    main()