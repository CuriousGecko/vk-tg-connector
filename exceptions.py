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


class MissingUserVkIdError(Exception):
    pass


class NoInterlocutorError(Exception):
    pass


class NoMessageForReply(Exception):
    pass
