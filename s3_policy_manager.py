import boto3
import json
import argparse
from botocore.exceptions import ClientError
import sys
from datetime import datetime
import os
import glob

def get_aws_account_id(sts_client=None):
    """Get the AWS account ID of the current session."""
    if sts_client is None:
        sts_client = boto3.client('sts')
    try:
        return sts_client.get_caller_identity()['Account']
    except Exception as e:
        print(f"Error getting AWS account ID: {str(e)}")
        sys.exit(1)

def ensure_backup_directory(account_id):
    """Create backup directory if it doesn't exist."""
    backup_dir = f"policy_backups_{account_id}"
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir

def ensure_policy_templates_directory():
    """Create policy templates directory if it doesn't exist."""
    templates_dir = "policy_templates"
    os.makedirs(templates_dir, exist_ok=True)
    return templates_dir

def list_and_select_buckets(s3_client):
    """List all buckets and allow user to select them by number."""
    try:
        buckets = s3_client.list_buckets()['Buckets']
        
        if not buckets:
            print("No S3 buckets found in your account.")
            sys.exit(1)
            
        print("\nAvailable buckets:")
        for i, bucket in enumerate(buckets, 1):
            print(f"{i}. {bucket['Name']}")
            
        while True:
            try:
                selection = input("\nEnter bucket numbers (comma-separated) or 'all': ").strip()
                
                if selection.lower() == 'all':
                    return [bucket['Name'] for bucket in buckets]
                
                selected_indices = [int(idx.strip()) for idx in selection.split(',')]
                selected_buckets = []
                
                for idx in selected_indices:
                    if idx < 1 or idx > len(buckets):
                        print(f"Invalid bucket number: {idx}")
                        continue
                    selected_buckets.append(buckets[idx-1]['Name'])
                
                if not selected_buckets:
                    print("No valid buckets selected. Please try again.")
                    continue
                    
                print("\nSelected buckets:")
                for bucket in selected_buckets:
                    print(f"- {bucket}")
                confirm = input("\nProceed with these buckets? (y/n): ").lower()
                if confirm == 'y':
                    return selected_buckets
                else:
                    print("Please select buckets again.")
                    
            except ValueError:
                print("Invalid input. Please enter comma-separated numbers or 'all'.")
            except IndexError:
                print("Invalid bucket number. Please try again.")
                
    except Exception as e:
        print(f"Error listing buckets: {str(e)}")
        sys.exit(1)

def get_current_policy(s3_client, bucket_name):
    """Get current bucket policy if it exists."""
    try:
        policy = s3_client.get_bucket_policy(Bucket=bucket_name)
        return json.loads(policy['Policy'])
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchBucketPolicy':
            return None
        raise

def load_policy_template(template_name, bucket_name):
    """Load and customize policy template for the specified bucket."""
    templates_dir = ensure_policy_templates_directory()
    template_path = os.path.join(templates_dir, f"{template_name}.json")
    
    try:
        with open(template_path, 'r') as f:
            template = json.load(f)
            
        # Replace placeholder values in the template
        def replace_placeholders(obj):
            if isinstance(obj, dict):
                return {k: replace_placeholders(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [replace_placeholders(item) for item in obj]
            elif isinstance(obj, str):
                return obj.replace("${bucket_name}", bucket_name)
            return obj
            
        return replace_placeholders(template)
    except FileNotFoundError:
        print(f"Policy template '{template_name}' not found in {templates_dir}")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Invalid JSON in policy template: {template_name}")
        sys.exit(1)

def backup_policy(policy, bucket_name, account_id):
    """Save the current policy to a backup file in account-specific directory."""
    if policy:
        backup_dir = ensure_backup_directory(account_id)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = os.path.join(backup_dir, f"bucket_policy_backup_{bucket_name}_{timestamp}.json")
        with open(filename, 'w') as f:
            json.dump(policy, f, indent=4)
        return filename
    return None

def list_policy_templates():
    """List available policy templates."""
    templates_dir = ensure_policy_templates_directory()
    templates = glob.glob(os.path.join(templates_dir, "*.json"))
    
    if not templates:
        print(f"\nNo policy templates found in {templates_dir}")
        print("Please add policy templates as JSON files in this directory.")
        sys.exit(1)
        
    print("\nAvailable policy templates:")
    for i, template in enumerate(templates, 1):
        template_name = os.path.splitext(os.path.basename(template))[0]
        print(f"{i}. {template_name}")
    
    return templates

def list_policy_backups(account_id, bucket_name=None):
    """List available policy backups for restoration."""
    backup_dir = ensure_backup_directory(account_id)
    pattern = f"bucket_policy_backup_{bucket_name}_*.json" if bucket_name else "bucket_policy_backup_*.json"
    backups = glob.glob(os.path.join(backup_dir, pattern))
    backups.sort(reverse=True)  # Most recent first
    
    if not backups:
        print(f"\nNo policy backups found in {backup_dir}")
        return None
        
    print("\nAvailable policy backups:")
    for i, backup in enumerate(backups, 1):
        print(f"{i}. {os.path.basename(backup)}")
    
    return backups

def apply_policy(bucket_list, template_name, backup=True, account_id=None):
    """Apply policy to specified buckets."""
    s3_client = boto3.client('s3')
    results = {}

    for bucket_name in bucket_list:
        try:
            # Get current policy
            current_policy = get_current_policy(s3_client, bucket_name)
            
            # Backup existing policy if requested
            backup_file = None
            if backup and current_policy:
                backup_file = backup_policy(current_policy, bucket_name, account_id)

            # Load policy template
            new_policy_statement = load_policy_template(template_name, bucket_name)
            
            # If there's an existing policy, check for duplicates and merge
            if current_policy:
                # Check if similar policy already exists
                policy_exists = any(
                    stmt.get('Sid') == new_policy_statement['Statement'][0]['Sid']
                    for stmt in current_policy['Statement']
                )
                
                if policy_exists:
                    results[bucket_name] = {
                        'status': 'skipped',
                        'message': f'Policy with Sid {new_policy_statement["Statement"][0]["Sid"]} already exists'
                    }
                    continue
                
                # Add new statement to existing policy
                current_policy['Statement'].extend(new_policy_statement['Statement'])
                final_policy = current_policy
            else:
                # Use new policy if none exists
                final_policy = new_policy_statement

            # Apply the policy
            s3_client.put_bucket_policy(
                Bucket=bucket_name,
                Policy=json.dumps(final_policy)
            )
            
            results[bucket_name] = {
                'status': 'success',
                'backup_file': backup_file
            }

        except Exception as e:
            results[bucket_name] = {
                'status': 'error',
                'error': str(e)
            }

    return results

def remove_policy(bucket_list, sid):
    """Remove policy with specified Sid from buckets."""
    s3_client = boto3.client('s3')
    results = {}

    for bucket_name in bucket_list:
        try:
            current_policy = get_current_policy(s3_client, bucket_name)
            
            if current_policy:
                # Remove the specified statement from policy
                original_count = len(current_policy['Statement'])
                current_policy['Statement'] = [
                    stmt for stmt in current_policy['Statement']
                    if stmt.get('Sid') != sid
                ]
                
                if len(current_policy['Statement']) == original_count:
                    results[bucket_name] = {
                        'status': 'skipped',
                        'message': f'No policy with Sid {sid} found'
                    }
                    continue
                
                # Update or delete policy based on remaining statements
                if current_policy['Statement']:
                    s3_client.put_bucket_policy(
                        Bucket=bucket_name,
                        Policy=json.dumps(current_policy)
                    )
                else:
                    s3_client.delete_bucket_policy(Bucket=bucket_name)
                
                results[bucket_name] = {'status': 'success'}
            else:
                results[bucket_name] = {
                    'status': 'skipped',
                    'message': 'No policy exists'
                }

        except Exception as e:
            results[bucket_name] = {
                'status': 'error',
                'error': str(e)
            }

    return results

def restore_policy(bucket_name, backup_file):
    """Restore a bucket policy from a backup file."""
    s3_client = boto3.client('s3')
    
    try:
        with open(backup_file, 'r') as f:
            policy = json.load(f)
        
        s3_client.put_bucket_policy(
            Bucket=bucket_name,
            Policy=json.dumps(policy)
        )
        return {'status': 'success'}
    except Exception as e:
        return {'status': 'error', 'error': str(e)}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Manage S3 bucket policies')
    parser.add_argument('action', choices=['apply', 'remove', 'restore', 'list-templates', 'list-backups'],
                       help='Action to perform')
    parser.add_argument('--template', help='Name of the policy template to apply')
    parser.add_argument('--sid', help='Policy Sid to remove')
    parser.add_argument('--bucket', help='Specific bucket for backup listing/restoration')
    parser.add_argument('--backup-file', help='Backup file to restore from')
    parser.add_argument('--no-backup', action='store_true',
                       help='Skip backing up existing policies')

    args = parser.parse_args()

    # Initialize S3 client and get AWS account ID
    s3_client = boto3.client('s3')
    account_id = get_aws_account_id()

    if args.action == 'list-templates':
        list_policy_templates()
        sys.exit(0)
        
    if args.action == 'list-backups':
        list_policy_backups(account_id, args.bucket)
        sys.exit(0)
        
    if args.action == 'restore':
        if not args.bucket or not args.backup_file:
            print("Both --bucket and --backup-file are required for restore action")
            sys.exit(1)
        result = restore_policy(args.bucket, args.backup_file)
        print(f"\nRestore result for {args.bucket}:")
        print(f"Status: {result['status']}")
        if result['status'] == 'error':
            print(f"Error message: {result['error']}")
        sys.exit(0)

    # Get bucket selection for apply/remove actions
    selected_buckets = list_and_select_buckets(s3_client)

    if args.action == 'apply':
        if not args.template:
            print("--template is required for apply action")
            sys.exit(1)
        results = apply_policy(selected_buckets, args.template, backup=not args.no_backup, account_id=account_id)
    elif args.action == 'remove':
        if not args.sid:
            print("--sid is required for remove action")
            sys.exit(1)
        results = remove_policy(selected_buckets, args.sid)

    # Print results
    print("\nOperation Results:")
    for bucket, result in results.items():
        print(f"\nBucket: {bucket}")
        if result['status'] == 'success':
            print("Status: Success")
            if 'backup_file' in result and result['backup_file']:
                print(f"Backup saved to: {result['backup_file']}")
        elif result['status'] == 'skipped':
            print(f"Status: Skipped - {result['message']}")
        else:
            print(f"Status: Error")
            print(f"Error message: {result['error']}")
