import React from 'react';
import { Link } from 'react-router-dom';
import { Button, Card } from '../UIComponents';

/** 需要处理的工作项：标题 + 数量说明 + 引导文案 + CTA。 */
export const OverviewWorkItem = ({
  title, count, description, cta, to,
}: {
  title: string;
  count: number;
  description: string;
  cta: string;
  to: string;
}) => (
  <Card className="ov-work-item">
    <div className="ov-work-main">
      <div className="ov-work-title">
        {title}
        {count > 0 && <span className="ov-work-count">{count}</span>}
      </div>
      <p className="ov-work-desc">{description}</p>
    </div>
    <div className="ov-work-action">
      {count > 0 ? (
        <Link to={to} className="ov-work-link">{cta} →</Link>
      ) : (
        <span className="ov-work-done">全部处理完成</span>
      )}
    </div>
  </Card>
);
