# Meta WhatsApp Cloud API

Set the Meta configuration variables in the backend environment. Keep the access token, webhook verify token, and app secret private. `META_WHATSAPP_PHONE_NUMBER_ID` is the sending number's ID, not the phone number itself.

Ticket-resolution messages use the approved WhatsApp template configured in `META_WHATSAPP_TEMPLATE_NAME` and `META_WHATSAPP_TEMPLATE_LANGUAGE`. The customer recipient is taken from the ticket's current opted-in WhatsApp contact. Do not configure a fixed test recipient.

To enable delivery statuses, configure the Meta webhook callback URL as `https://<host>/api/whatsapp/webhook/`, subscribe it to `messages`, and set `META_WHATSAPP_VERIFY_TOKEN` to the same verify token used during webhook setup. Configure `META_WHATSAPP_APP_SECRET` with the Meta app secret so incoming webhook signatures can be verified.

On a test ticket, record customer WhatsApp consent and an international number, then resolve the ticket. The notification panel tracks provider acceptance and later sent, delivered, read, or failed webhook statuses. Transient Graph API/network errors keep the existing bounded retry behavior; failed notifications can be manually retried after correcting the cause.
