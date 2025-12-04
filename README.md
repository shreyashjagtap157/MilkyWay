# MilkyWay 🥛

A comprehensive Django-based web application for managing milk delivery services and home solutions. MilkyWay streamlines the entire milk delivery ecosystem by connecting customers, vendors, milkmen, and administrators on a single platform.

## 🌟 Features

### Customer Management
- Customer registration and profile management
- Subscription management for milk delivery
- Delivery history tracking
- Real-time order updates

### Vendor Management
- Business registration for vendors
- Vendor login and authentication
- Calendar-based delivery scheduling
- Inventory and product management

### Milkman Interface
- Dedicated portal for delivery personnel
- Route optimization
- Delivery confirmation and tracking

### Admin Dashboard
- Centralized system administration
- User management
- Analytics and reporting
- Business insights

### Additional Features
- Comprehensive reporting system
- Delivery history tracking
- One-window home solution services
- Multi-user role management

## 🛠️ Tech Stack

- **Framework:** Django (Python)
- **Backend:** Django ORM
- **Deployment:** Passenger WSGI
- **Version Control:** Git

## 📁 Project Structure

```
MilkyWay/
├── BusinessRegistration/   # Vendor business registration module
├── Customer/              # Customer management
├── Dashboard/             # Admin dashboard
├── Deliveryhistory/       # Delivery tracking and history
├── Milkman/              # Milkman portal
├── OneWindowHomeSolution/ # Main Django project settings
├── Report/               # Reporting and analytics
├── Subscription/         # Subscription management
├── Systemadmin/          # System administration
├── vendor/               # Vendor module
├── vendor_login/         # Vendor authentication
├── vendorcalendar/       # Vendor scheduling
├── utils/                # Utility functions
├── logs/                 # Application logs
├── manage.py             # Django management script
└── passenger_wsgi.py     # WSGI configuration
```

## 🚀 Getting Started

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- Virtual environment (recommended)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/shreyashjagtap157/MilkyWay.git
cd MilkyWay
```

2. **Create and activate virtual environment**
```bash
python -m venv venv

# On Windows
venv\Scripts\activate

# On macOS/Linux
source venv/bin/activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Run migrations**
```bash
python manage.py makemigrations
python manage.py migrate
```

5. **Create superuser (admin)**
```bash
python manage.py createsuperuser
```

6. **Run the development server**
```bash
python manage.py runserver
```

7. **Access the application**
- Open your browser and navigate to `http://127.0.0.1:8000/`
- Admin panel: `http://127.0.0.1:8000/admin/`

## 🔧 Configuration

Update the `OneWindowHomeSolution/settings.py` file with your specific configurations:

- Database settings
- Secret key
- Allowed hosts
- Static files configuration
- Email backend settings (for notifications)

## 📊 Modules

### 1. Customer Module
Handles customer-related operations including registration, profile management, and order placement.

### 2. Vendor Module
Manages vendor operations, business registration, and product listings.

### 3. Subscription Module
Handles recurring milk delivery subscriptions with flexible scheduling options.

### 4. Milkman Module
Provides delivery personnel with route information and delivery management tools.

### 5. Dashboard
Centralized control panel for administrators with analytics and system management.

### 6. Reporting
Generate comprehensive reports on deliveries, subscriptions, and business metrics.

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 👤 Author

**Shreyash Jagtap**
- GitHub: [@shreyashjagtap157](https://github.com/shreyashjagtap157)
- Location: Pune, India

## 🙏 Acknowledgments

- Django framework and community
- All contributors who have helped shape this project

## 📧 Contact

For any queries or support, please open an issue on GitHub or reach out through the repository.

---

⭐ If you find this project useful, please consider giving it a star on GitHub!