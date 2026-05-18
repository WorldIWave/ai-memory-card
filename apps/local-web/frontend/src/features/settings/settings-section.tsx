/**
 * Input: section ?????? children  |  Output: ???????????
 * Output: ??????????????????? section ??
 * Role: ????????????????
 * Use: ???????????????????????????
 */
import type { ReactNode } from "react";
import { Card } from "../../components/ui";
import { cn } from "../../lib/utils";

interface SettingsSectionProps {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  hidden?: boolean;
}

export function SettingsSection({ title, description, action, children, className, hidden }: SettingsSectionProps) {
  return (
    <Card className={cn("settings-section-card", className)} panel hidden={hidden}>
      <div className="settings-card-header">
        <div>
          <h3>{title}</h3>
          {description ? <p>{description}</p> : null}
        </div>
        {action}
      </div>
      <div className="settings-section-body">{children}</div>
    </Card>
  );
}
