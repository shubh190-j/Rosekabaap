class Production(Config):
    LOGGER = False
    WEBHOOK = True
    URL = os.environ.get('URL')  # Your Render app URL
    PORT = int(os.environ.get('PORT', 8443))
