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
"""
ETL Addon for Apache Superset

Provides scheduled or one-time ETL jobs that fetch CSV/TSV/Excel files
from remote URLs and import them into a configured Superset database.

Registration
------------
Add to superset_config.py:

    from addons.etl import init_etl_addon
    # Called inside a custom SupersetAppInitializer.init_views():
    #   init_etl_addon(appbuilder)

Or with the simpler FLASK_APP_MUTATOR hook — see the README for details.

Feature flag
------------
    FEATURE_FLAGS = {"ENABLE_ETL_JOBS": True}
"""
