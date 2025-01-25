import requests
from datetime import datetime, timezone
from umich.getsecrets import get_secret


mcommunity_api = 'https://mcommunity.umich.edu/api'


class MCommunity:

    def __init__(self, *, username, secret_name):
        self.username = username
        self.secret_name = secret_name
        self.auth_headers = None

    def connect(self):
        try:
            r = requests.post(
                url=f'{mcommunity_api}/token/',
                data={
                    'username': self.username,
                    'password': get_secret(self.secret_name)
                }
            )
            response_dict = r.json()
        except Exception as e:
            raise RuntimeError(f'Error obtaining MCommunity API token: {e}')

        if 'access' not in response_dict:
            raise RuntimeError(f'MCommunity did not return an access token ({r.status_code}): {response_dict}')
        access_token = response_dict['access']
        self.auth_headers = {'Authorization': f'Bearer {access_token}'}

    def get_members(self, cn, member_type='member'):
        """
        Get the members of an MCommunity group.

        :param cn: The MCommunity group's cn (common name).
        :param member_type: The type of members to return.  Valid values are 'member' and 'umichDirectGroupMember'.
        :return: A list of members.

        NOTE: when using the MCommunity API, "member" is actually only direct members, not members of subgroups.
        This is different from LDAP where "member" is all members, including members of subgroups, and it is also
        different from how the MCommunity API handles groups (where "groupMember" includes all subgroups but
        "umichDirectGroupMember" does not include subgroups).  There is no "umichDirectMember" field for
        MCommunity API group query results and no way to get the members of subgroups without making multiple queries.
        """
        if self.auth_headers is None:
            self.connect()

        group_uri = f'{mcommunity_api}/groups/{cn}/'
        try:
            r = requests.get(group_uri, headers=self.auth_headers)
        except Exception as e:
            raise RuntimeError(f'Error querying MCommunity group "{cn}": {e}')
        if r.status_code != 200:
            raise RuntimeError(f'Error querying MCommunity group "{cn}": HTTP {r.status_code} {r.text}')
        g = r.json()

        # Refuse to use the group if it might be insecure:
        if 'cn=ITS Cloudflare Admins,ou=User Groups,ou=Groups,dc=umich,dc=edu' not in g.get('owner', []):
            raise AttributeError(f'untrustworthy group: "{cn}", "ITS Cloudflare Admins" is not an owner')
        if g.get('umichPrivate', False) is not True:
            raise AttributeError(f'untrustworthy group: "{cn}" is not private')
        if g.get('joinable', True) is not False:
            raise AttributeError(f'untrustworthy group: "{cn}" is joinable')

        expires = g.get('umichExpiryTimestamp', '1970-01-01T00:00:00Z')
        dt = datetime.strptime(expires, '%Y-%m-%dT%H:%M:%SZ')
        dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        expires_in = (dt - now).total_seconds()
        if expires_in < 7 * 24 * 60 * 60:
            raise AttributeError(f'untrustworthy group: "{cn}" is expiring or has expired')

        members = []
        for m in g.get(member_type, []):  # only use direct members, omit members of subgroups
            if 'umichDirectGroupMember' == member_type:
                members.append(m.split(',')[0].split('cn=')[1])
            else:
                members.append(m.split(',')[0].split('uid=')[1] + '@umich.edu')
        return members

    def close(self):
        self.auth_headers = None
