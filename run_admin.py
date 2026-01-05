from Admin.adminpanel import create_admin_app

if __name__ == "__main__":
    app = create_admin_app()
    print("Starting admin panel on http://127.0.0.1:8080")
    print("Credentials: admin / change_me")
    app.run(host="127.0.0.1", port=8080, debug=False)
