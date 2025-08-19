# Deployment Guide

## Prerequisites
- Python 3.9+
- PostgreSQL database
- AWS Cognito User Pool configured

## Local Development Setup

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd AB3_VideoGame_Demo
   ```

2. **Create virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.template .env
   # Edit .env with your actual values
   ```

5. **Run database migrations**
   ```bash
   cd server
   python manage.py migrate
   ```

6. **Start the server**
   ```bash
   python __main__.py
   ```

## AWS EC2 Deployment

### Security Considerations
- Use AWS Secrets Manager for production secrets
- Deploy behind Application Load Balancer with SSL
- Use private subnets for EC2 instances
- Configure security groups with minimal required access

### Deployment Steps
1. Create IAM role with necessary permissions
2. Launch EC2 instance with the IAM role
3. Install dependencies and deploy code
4. Configure Application Load Balancer
5. Set up auto-scaling group

## Security Features
- Environment variables for sensitive data
- Secure path handling
- Input validation
- AWS Cognito authentication
- Database connection security