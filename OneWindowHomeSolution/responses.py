from rest_framework.response import Response
from rest_framework import status

def api_response(status_code, message, data=None, status_text="success"):
    """
    Helper function to create a standardized API response.
    """
    response_data = {
        "status": status_text,
        "code": status_code,
        "message": message,
    }
    if data is not None:
        response_data["data"] = data
    return Response(response_data, status=status_code)

def success_response(message, data=None, status_code=status.HTTP_200_OK):
    return api_response(status_code, message, data, "success")

def error_response(message, data=None, status_code=status.HTTP_400_BAD_REQUEST):
    return api_response(status_code, message, data, "error")

def not_found_response(message="Not found.", data=None):
    return error_response(message, data, status.HTTP_404_NOT_FOUND)
