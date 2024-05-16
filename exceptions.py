class LongPollResponseError(Exception):
    pass


class LongPollConnectionError(Exception):
    pass


class VkApiConnectionError(Exception):
    pass


class VkApiError(Exception):
    pass


class NoDataInResponseError(Exception):
    pass


class MissingMessageIdError(Exception):
    pass


class MissingUserVkIdIdError(Exception):
    pass
