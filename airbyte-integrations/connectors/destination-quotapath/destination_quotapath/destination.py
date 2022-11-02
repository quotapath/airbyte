#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#

from collections import defaultdict
import requests
from typing import Any, Iterable, Mapping

from airbyte_cdk import AirbyteLogger
from airbyte_cdk.destinations import Destination
from airbyte_cdk.models import AirbyteConnectionStatus, AirbyteMessage, ConfiguredAirbyteCatalog, Status, Type


SOURCE_DATA_ID_FIELDS = {"salesforce": "Id"}


class DestinationQuotapath(Destination):
    def write(
        self, config: Mapping[str, Any], configured_catalog: ConfiguredAirbyteCatalog, input_messages: Iterable[AirbyteMessage]
    ) -> Iterable[AirbyteMessage]:

        """
        Reads the input stream of messages, config, and catalog to write data to the destination.

        This method returns an iterable (typically a generator of AirbyteMessages via yield) containing state messages received
        in the input message stream. Outputting a state message means that every AirbyteRecordMessage which came before it has been
        successfully persisted to the destination. This is used to ensure fault tolerance in the case that a sync fails before fully completing,
        then the source is given the last state message output from this method as the starting point of the next sync.

        :param config: dict of JSON configuration matching the configuration declared in spec.json
        :param configured_catalog: The Configured Catalog describing the schema of the data being received and how it should be persisted in the
                                    destination
        :param input_messages: The stream of input messages received from the source
        :return: Iterable of AirbyteStateMessages wrapped in AirbyteMessage structs
        """

        records = defaultdict(list)
        upsert_url = config["quotapathHost"] + config["dataUpsertPath"]

        def write_to_api(records: dict[list[dict]]):
            if records:
                for (data_source, data_type), data_records in records.items():
                    print(f"About to write to data_source: {data_source}, data_type: {data_type}, data: {data_records}")
                    result = requests.post(
                        upsert_url,
                        json={
                            "data_source": data_source,
                            "data_type": data_type,
                            "data_id_field": SOURCE_DATA_ID_FIELDS.get(data_source, "id"),
                            "data": data_records,
                        },
                        headers={"Authorization": f"Token {config['apiKey']}"},
                    )
                    try:
                        result.raise_for_status()
                    except Exception as e:
                        print(f"http error: {result.text}")
                records.clear()

        for message in input_messages:
            print(f"message: {message}")
            if message.type == Type.STATE:
                # Emitting a state message indicates that all records which came before it have been written to the destination. So we flush
                # the queue to ensure writes happen, then output the state message to indicate it's safe to checkpoint state
                write_to_api(records)
                yield message
            elif message.type == Type.RECORD:
                record = message.record
                if record:
                    records[(record.namespace, record.stream)].append(record.data)
            else:
                # ignore other message types for now
                continue

        # Make sure to flush any records still in the queue
        write_to_api(records)

    def check(self, logger: AirbyteLogger, config: Mapping[str, Any]) -> AirbyteConnectionStatus:
        """
        Tests if the input configuration can be used to successfully connect to the destination with the needed permissions
            e.g: if a provided API token or password can be used to connect and write to the destination.

        :param logger: Logging object to display debug/info/error to the logs
            (logs will not be accessible via airbyte UI if they are not passed to this logger)
        :param config: Json object containing the configuration of this destination, content of this json is as specified in
        the properties of the spec.json file

        :return: AirbyteConnectionStatus indicating a Success or Failure
        """
        try:
            result = requests.get(
                config["quotapathHost"] + config["connectionTestPath"], headers={"Authorization": f"Token {config['apiKey']}"}
            )
            result.raise_for_status()
            logger.info(f"Connection successful, response: {result.json()}")
            return AirbyteConnectionStatus(status=Status.SUCCEEDED)
        except Exception as e:
            logger.exception(e)
            return AirbyteConnectionStatus(status=Status.FAILED, message=f"An exception occurred: {repr(e)}")
