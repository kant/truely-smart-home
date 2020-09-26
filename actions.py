import pandas as pd
import sonoff

from config import dbConfig, switchCloudControl
from db import db

with db(**dbConfig) as DB:
    DB.create_schema('action')
    DB.session.execute("""CREATE TABLE IF NOT EXISTS action.action(
            action_id SERIAL PRIMARY KEY
            , created_at DATETIME WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            , action_time DATETIME NOT NULL
            , device_id VARCHAR(100) NOT NULL
            , action VARCHAR(100) NOT NULL
            , actioned_at DATETIME
            , cancelled BIT DEFAULT 0
            )
        """)
    DB.session.commit()


class action:
    DB = db(**dbConfig)
    sonoff_account = sonoff.Sonoff(switchCloudControl['username'],
                                   switchCloudControl['password'],
                                   switchCloudControl['api_region'])

    def check_multi_action(self):
        """
        If multiple commands for single device at single time, cancel all but the most recent.
        """

        self.DB.session.execute("""
            UPDATE action.action AS a
            SET cancelled = 1
            LEFT JOIN (
                SELECT action_time, device_id, MAX(action_id) AS actionable_id
                FROM action.action
                WHERE cencelled = 0
                GROUP BY action_time, device_id
                HAVING COUNT(*) > 1
            ) AS s
                ON s.action_time = a.action_time
                    AND s.device_id = a.device_id
            WHERE s.action_time IS NULL
                OR a.action_id = s.actionable_id
            """)
        self.DB.session.commit()

    @property
    def actions(self) -> pd.DataFrame:
        return pd.read_sql("""
            SELECT action_id, action_time, device_id, action
            FROM action.action
            WHERE actioned_at IS NULL
                AND action_time <= CURRENT_TIMESTAMP
                AND cancelled = 0
        """, self.DB.connection)

    def execute_todo(self):
        self.check_multi_action()

        for item in self.actions.iterrows():
            self.sonoff_account.switch(item.action, item.device_id)

            self.DB.session.execute(f"""
                UPDATE action.action
                SET actioned_at = CURRENT_TIMESTAMP
                WHERE action_id = {item.action_id}
            """)
        self.DB.session.commit()