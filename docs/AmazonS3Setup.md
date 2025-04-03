# Setting up Amazon S3 Integration

This guide explains how to set up the Amazon S3 integration for DocuElevate.

## Required Configuration Parameters

| **Variable**                    | **Description**                                       |
|---------------------------------|-------------------------------------------------------|
| `AWS_ACCESS_KEY_ID`             | AWS IAM access key ID                                 |
| `AWS_SECRET_ACCESS_KEY`         | AWS IAM secret access key                             |
| `AWS_REGION`                    | AWS region where your S3 bucket is located (default: `us-east-1`) |
| `S3_BUCKET_NAME`                | Name of your S3 bucket                                |
| `S3_FOLDER_PREFIX`              | Optional prefix/folder path for uploaded files        |
| `S3_STORAGE_CLASS`              | Storage class for uploaded objects (default: `STANDARD`) |
| `S3_ACL`                        | Access control for uploaded files (default: `private`) |

For a complete list of configuration options, see the [Configuration Guide](ConfigurationGuide.md).

## Step-by-Step Setup Instructions

### 1. Create an S3 bucket

1. Go to the [Amazon S3 Console](https://s3.console.aws.amazon.com/)
2. Click "Create bucket"
3. Enter a globally unique name for your bucket
4. Select your preferred AWS region
5. Configure other settings as needed (block public access is recommended)
6. Click "Create bucket"

### 2. Create an IAM User with S3 Access

1. Go to the [AWS IAM Console](https://console.aws.amazon.com/iam/)
2. Navigate to "Users" and click "Add users"
3. Enter a name (e.g., "docuelevate-s3-access")
4. For access type, select "Programmatic access"
5. Click "Next: Permissions"
6. Choose "Attach existing policies directly" and search for "AmazonS3FullAccess"
7. For more security, you can create a custom policy limiting access to just your bucket
8. Click through to review and create the user
9. On the final page, you'll see the Access Key ID and Secret Access Key
10. Save these credentials securely as they won't be shown again

### 3. Configure DocuElevate

1. Set `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` to the credentials from step 2
2. Set `AWS_REGION` to the region where your bucket was created (e.g., "us-east-1")
3. Set `S3_BUCKET_NAME` to your bucket name
4. Set `S3_FOLDER_PREFIX` to organize files in specific subfolder paths (e.g., "invoices/" or "documents/2023/")
5. Optionally customize `S3_STORAGE_CLASS` and `S3_ACL` for your storage needs

### 4. Optional: Create a Custom IAM Policy (for better security)

1. In IAM console, go to "Policies" and click "Create policy"
2. Use the JSON editor and paste a policy like this (replace `your-bucket-name`):
   ```json
   {
       "Version": "2012-10-17",
       "Statement": [
           {
               "Effect": "Allow",
               "Action": [
                   "s3:PutObject",
                   "s3:GetObject",
                   "s3:ListBucket"
               ],
               "Resource": [
                   "arn:aws:s3:::your-bucket-name",
                   "arn:aws:s3:::your-bucket-name/*"
               ]
           }
       ]
   }
   ```
3. After creating the policy, attach it to your user instead of the broader AmazonS3FullAccess

## Storage Class Options

Amazon S3 offers several storage classes to optimize costs:

| **Storage Class** | **Use Case** | **Retrieval Time** |
|------------------|--------------|-------------------|
| `STANDARD` | Default, frequently accessed data | Immediate |
| `INTELLIGENT_TIERING` | Data with changing or unknown access patterns | Immediate |
| `STANDARD_IA` | Long-lived, infrequently accessed data | Immediate |
| `ONEZONE_IA` | Long-lived, infrequently accessed, non-critical data | Immediate |
| `GLACIER_IR` | Archive data that needs immediate access | Immediate |
| `GLACIER` | Archive data that rarely needs to be accessed | Minutes to hours |
| `DEEP_ARCHIVE` | Long-term archive and digital preservation | Hours |

Set your preferred storage class using the `S3_STORAGE_CLASS` parameter.

## Access Control List (ACL) Options

Common ACL values include:

- `private` (default) - Only the bucket owner has access
- `public-read` - Anyone can read the file (use cautiously)
- `bucket-owner-full-control` - Useful for cross-account uploads

For most document storage scenarios, `private` is recommended for security.
