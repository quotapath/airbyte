#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#


import sys

from destination_quotapath import DestinationQuotapath

if __name__ == "__main__":
    DestinationQuotapath().run(sys.argv[1:])
