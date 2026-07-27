/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { FormEvent } from "react";
import { useEffect, useState } from "react";
import { Timer } from "lucide-react";
// plane imports
import { Button } from "@plane/propel/button";
import { Input, TextArea } from "@plane/ui";
import { convertHoursMinutesToMinutes } from "@plane/utils";
import type { TWorklog } from "@plane/types";

type TWorklogFormValues = {
  hours: string;
  minutes: string;
  description: string;
};

type Props = {
  data: TWorklogFormValues;
  onSubmit: (payload: Partial<TWorklog>) => Promise<void>;
  onCancel: () => void;
  buttonDisabled?: boolean;
  buttonTitle: string;
};

export function WorklogForm(props: Props) {
  const { data, onSubmit, onCancel, buttonDisabled = false, buttonTitle } = props;
  const [formData, setFormData] = useState<TWorklogFormValues>(data);
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    setFormData(data);
  }, [data]);

  const handleChange = <K extends keyof TWorklogFormValues>(key: K, value: TWorklogFormValues[K]) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
    setHasError(false);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const hours = Number(formData.hours) || 0;
    const minutes = Number(formData.minutes) || 0;
    if (!hours && !minutes) {
      setHasError(true);
      return;
    }
    await onSubmit({
      duration: Math.round(convertHoursMinutesToMinutes(hours, minutes)),
      description: formData.description || "",
    });
  };

  return (
    <form onSubmit={(e) => void handleSubmit(e)} className="space-y-2">
      <div className="inline-flex items-center gap-1 rounded-full bg-layer-2 px-2.5 py-1.5 text-caption-sm-medium text-secondary">
        <Timer className="size-3" />
        <span>
          {formData.hours || 0}h {formData.minutes || 0}m
        </span>
      </div>

      <div className="flex items-center">
        <Input
          id="worklog-hours"
          type="number"
          name="hours"
          placeholder="Hours"
          value={formData.hours}
          onChange={(e) => handleChange("hours", e.target.value)}
          hasError={hasError}
          className="w-full rounded-r-none"
          autoFocus
          min={0}
          step="any"
        />
        <Input
          id="worklog-minutes"
          type="number"
          name="minutes"
          placeholder="Minutes"
          value={formData.minutes}
          onChange={(e) => handleChange("minutes", e.target.value)}
          hasError={hasError}
          className="w-full rounded-l-none border-l-0"
          min={0}
        />
      </div>

      <TextArea
        id="worklog-description"
        name="description"
        placeholder="Description"
        value={formData.description}
        onChange={(e) => handleChange("description", e.target.value)}
        className="min-h-24 w-full resize-none text-body-xs-regular"
      />

      <div className="flex items-center justify-end gap-2">
        <Button type="button" variant="secondary" size="sm" disabled={buttonDisabled} onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" size="sm" disabled={buttonDisabled} loading={buttonDisabled}>
          {buttonTitle}
        </Button>
      </div>
    </form>
  );
}
