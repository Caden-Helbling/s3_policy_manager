# s3_policy_manager
A Python script for managing AWS S3 bucket policies across multiple buckets. This tool allows you to apply, remove, and restore bucket policies using templates, with automatic backup functionality.

## Features

- Apply policy templates to multiple S3 buckets
- Remove specific policies by SID
- Backup existing policies before modifications
- Restore policies from backups
- Interactive bucket selection
- Template-based policy management
- Policy deduplication (prevents duplicate policy statements)

## Prerequisites

- Python 3.x
- AWS credentials configured (via AWS CLI, environment variables, or IAM role)
- Required Python packages:
  ```
  boto3
  ```

## Installation

1. Clone this repository or download the script
2. Install required packages:
   ```bash
   pip install boto3
   ```
3. Create a `policy_templates` directory in the same location as the script

## Directory Structure

```
.
├── s3_policy_manager.py
├── policy_templates/
│   ├── template1.json
│   └── template2.json
└── policy_backups_<account_id>/
    └── bucket_policy_backup_<bucket_name>_<timestamp>.json
```

## Usage

### General Command Structure

```bash
python s3_policy_manager.py <action> [options]
```

### Available Actions

1. **Apply a Policy Template**
   ```bash
   python s3_policy_manager.py apply --template <template_name>
   ```

2. **Remove a Policy**
   ```bash
   python s3_policy_manager.py remove --sid <policy_sid>
   ```

3. **List Available Templates**
   ```bash
   python s3_policy_manager.py list-templates
   ```

4. **List Policy Backups**
   ```bash
   python s3_policy_manager.py list-backups [--bucket <bucket_name>]
   ```

5. **Restore a Policy from Backup**
   ```bash
   python s3_policy_manager.py restore --bucket <bucket_name> --backup-file <path_to_backup>
   ```

### Options

- `--template`: Name of the policy template to apply (required for `apply` action)
- `--sid`: Policy Statement ID to remove (required for `remove` action)
- `--bucket`: Specific bucket name for backup listing/restoration
- `--backup-file`: Path to the backup file for restoration
- `--no-backup`: Skip backing up existing policies before modification

## Policy Templates

### Template Format

Policy templates should be JSON files stored in the `policy_templates` directory. Templates can include the placeholder `${bucket_name}` which will be replaced with the actual bucket name during application.

Example template (`policy_templates/example_policy.json`):
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "ExamplePolicy",
            "Effect": "Allow",
            "Principal": {
                "AWS": "*"
            },
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::${bucket_name}/*"
        }
    ]
}
```

## Backup System

- Backups are automatically created before applying new policies
- Backup files are stored in `policy_backups_<account_id>` directory
- Backup filenames include bucket name and timestamp
- Use `list-backups` to view available backups
- Use `restore` action to revert to a previous policy state

## Error Handling

The script includes comprehensive error handling for:
- AWS API errors
- Invalid bucket selections
- Missing or invalid templates
- Policy application failures
- Backup/restore operations

## Security Notes

- The script requires appropriate AWS IAM permissions for S3 bucket policy operations
- Always review policy templates before application
- Use `--no-backup` with caution as it skips policy backup creation

## Best Practices

1. Always maintain backups of critical bucket policies
2. Test policy changes on non-production buckets first
3. Review generated backups before applying major changes
4. Use descriptive SIDs in policy templates for easier management

## Troubleshooting

If you encounter issues:

1. Verify AWS credentials are properly configured
2. Check IAM permissions for S3 bucket policy operations
3. Ensure policy templates are valid JSON
4. Verify template directory structure
5. Check backup directory permissions
