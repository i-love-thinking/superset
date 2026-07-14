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
from __future__ import annotations

from flask_appbuilder.models.filters import BaseFilter
from sqlalchemy import or_

from superset.utils.core import get_user_id


class EtlJobAccessFilter(BaseFilter):
    """
    Allow access to ETL jobs where:
    - the current user is the creator, OR
    - the user has Admin or Alpha roles (handled at the FAB permission level)
    """

    name = "ETL Job Access"
    arg_name = "etl_job_access"

    def apply(self, query: any, value: any) -> any:  # type: ignore
        from addons.etl.models import EtlJob

        user_id = get_user_id()
        if user_id is None:
            return query.filter(False)

        return query.filter(
            or_(
                EtlJob.created_by_fk == user_id,
            )
        )
