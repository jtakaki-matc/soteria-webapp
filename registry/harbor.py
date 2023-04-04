"""
Wrapper for Harbor's API.
"""

import logging
from typing import Optional, Tuple, Union

import requests

__all__ = ["HarborAPI"]


class HarborAPI:
    """
    Wrapper for Harbor's API.

    All calls will be made using the credentials provided to the constructor.
    """

    def __init__(
        self,
        api_base_url: str,
        basic_auth: Optional[Tuple[str, str]] = None,
    ):
        """
        Constructs a wrapper that uses the provided credentials.

        If a username and password are provided via `basic_auth`, API calls
        will be made using Basic authentication.
        """
        self._api_base_url = api_base_url
        self._basic_auth = basic_auth

        self._session = requests.Session()

        self._log = logging.getLogger(__name__)
        self._log.addHandler(logging.NullHandler())

    def _renew_session(self) -> None:
        """
        Hack for avoiding tracking XSRF tokens.
        """
        if self._session:
            self._session.close()
        self._session = requests.Session()

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Logs and sends an HTTP request.

        Keyword arguments are passed through unmodified to the `requests`
        library's `request` method. If the response contains an error
        status code, the response is still returned. Other failures result
        in an exception being raised.
        """
        if self._basic_auth:
            if "auth" not in kwargs:
                kwargs["auth"] = self._basic_auth

        self._log.info("%s %s", method.upper(), url)

        try:
            r = self._session.request(method, url, **kwargs)
        except requests.RequestException:
            self._log.exception("Unexpected `requests` error")
            raise

        # NOTE: Responses can include secrets, so it is not safe to log them
        # here without sanitizing them.

        try:
            r.raise_for_status()
        except requests.HTTPError as exn:
            self._log.info("HTTP Error: %s", exn)

        return r

    def _delete(self, route: str, **kwargs) -> requests.Response:
        """
        Logs and sends an HTTP DELETE request for the given route.
        """
        self._renew_session()

        return self._request("DELETE", f"{self._api_base_url}{route}", **kwargs)

    def _get(self, route: str, **kwargs) -> requests.Response:
        """
        Logs and sends an HTTP GET request for the given route.
        """
        return self._request("GET", f"{self._api_base_url}{route}", **kwargs)

    def _head(self, route: str, **kwargs) -> requests.Response:
        """
        Logs and sends an HTTP HEAD request for the given route.
        """
        return self._request("HEAD", f"{self._api_base_url}{route}", **kwargs)

    def _post(self, route: str, **kwargs) -> requests.Response:
        """
        Logs and sends an HTTP POST request for the given route.
        """
        self._renew_session()

        return self._request("POST", f"{self._api_base_url}{route}", **kwargs)

    #
    # ----------------------------------------------------------------------
    #

    def get_user(self, user_id: int):
        """
        Returns a user's profile.
        """
        return self._get(f"/users/{user_id}").json()

    def get_all_users(self):
        """
        Returns a list of all users.

        Might not include data populated via OIDC.
        """
        # FIXME (baydemir): Page through the results, and yield one at a time.
        params = {
            "page_size": 100,
            "sort": "-update_time",
        }
        return self._get("/users", params=params).json()

    def search_for_user(self, email: str, subiss: str):
        """
        Returns a user with the given email address and "subiss".
        """
        params = {
            "page_size": 100,
            "q": f"email=~{email}",  # email addresses are not case sensitive
        }
        users = self._get("/users", params=params).json()

        for u in users:
            user = self.get_user(u["user_id"])

            if user.get("oidc_user_meta", {}).get("subiss", "") == subiss:
                return user

        return None

    #
    # ----------------------------------------------------------------------
    #

    def create_project(self, name: str, *, storage_limit: int = 5368709120):
        # 5 GiB = 5368709120 bytes = 5 * 1024 * 1024 * 1024
        """
        Create a new private project, with the given user as an administrator.
        """
        payload = {
            "project_name": name,
            "public": False,
            "storage_limit": storage_limit,
        }
        r = self._post("/projects", json=payload)

        if not r.ok:
            return r.json()
        return self.get_project(name)

    def get_project(self, project_id_or_name: Union[int, str]):
        """
        Get a new project, either by ID or by name.
        """
        return self._get(f"/projects/{project_id_or_name}").json()

    #
    # ----------------------------------------------------------------------
    #

    def add_project_member(
        self,
        project_id: int,
        username: str,
        role_id: int = 2,
    ):
        payload = {
            "role_id": role_id,
            "member_user": {"username": username},
        }

        r = self._post(f"/projects/{project_id}/members", json=payload)

        if not r.ok:
            return r.json()
        return self.get_project_member(project_id, username)

    def get_project_member(self, project_id: int, username: str):
        params = {"entityname": username}

        r = self._get(f"/projects/{project_id}/members", params=params).json()

        for member in r:
            if member["entity_name"] == username:
                return member
        return None

    def delete_project_member(self, project_id: int, username: str):
        member = self.get_project_member(project_id, username)

        r = self._delete(f"/projects/{project_id}/members/{member['id']}")

        if not r.ok:
            return r.json()
        return {}
