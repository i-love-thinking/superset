# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
from superset.commands.exceptions import CommandException, CommandInvalidError


class EtlJobNotFoundError(CommandException):
    status = 404
    message = "ETL job not found"


class EtlJobNameAlreadyExistsError(CommandInvalidError):
    status = 422
    message = "An ETL job with this name already exists"


class EtlJobCreateFailedError(CommandException):
    status = 422
    message = "ETL job could not be created"


class EtlJobUpdateFailedError(CommandException):
    status = 422
    message = "ETL job could not be updated"


class EtlJobDeleteFailedError(CommandException):
    status = 422
    message = "ETL job could not be deleted"


class EtlJobExecuteFailedError(CommandException):
    status = 500
    message = "ETL job execution failed"


class EtlJobUrlNotAllowedError(CommandException):
    status = 400
    message = "One or more source URLs are not allowed by the server configuration"


class EtlJobDatabaseNotFoundError(CommandException):
    status = 422
    message = "Target database not found"


class EtlJobInvalidCrontabError(CommandInvalidError):
    status = 422
    message = "Invalid cron expression"
