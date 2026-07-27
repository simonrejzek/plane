/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useForm } from "react-hook-form";
import { Lightbulb } from "lucide-react";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { IFormattedInstanceConfiguration, TInstanceAIConfigurationKeys } from "@plane/types";
// components
import type { TControllerInputFormField } from "@/components/common/controller-input";
import { ControllerInput } from "@/components/common/controller-input";
// hooks
import { useInstance } from "@/hooks/store";

type IInstanceAIForm = {
  config: IFormattedInstanceConfiguration;
};

type AIFormValues = Record<TInstanceAIConfigurationKeys, string>;

export function InstanceAIForm(props: IInstanceAIForm) {
  const { config } = props;
  // store
  const { updateInstanceConfigurations } = useInstance();
  // form data
  const {
    handleSubmit,
    control,
    formState: { errors, isSubmitting },
  } = useForm<AIFormValues>({
    defaultValues: {
      LLM_API_KEY: config["LLM_API_KEY"],
      LLM_MODEL: config["LLM_MODEL"],
      LLM_PROVIDER: config["LLM_PROVIDER"] || "custom",
      LLM_BASE_URL: config["LLM_BASE_URL"] || "",
    },
  });

  const aiFormFields: TControllerInputFormField[] = [
    {
      key: "LLM_PROVIDER",
      type: "text",
      label: "Provider",
      description: (
        <>
          Use <code className="text-12">custom</code> for any OpenAI-compatible endpoint (OpenRouter, vLLM, Azure-style
          proxies, etc.). Also supports <code className="text-12">openai</code>,{" "}
          <code className="text-12">anthropic</code>, and <code className="text-12">gemini</code>.
        </>
      ),
      placeholder: "custom",
      error: Boolean(errors.LLM_PROVIDER),
      required: false,
    },
    {
      key: "LLM_BASE_URL",
      type: "text",
      label: "Custom endpoint (BYOK)",
      description: (
        <>
          OpenAI-compatible base URL for your provider or proxy (e.g.{" "}
          <code className="text-12">https://openrouter.ai/api/v1</code> or{" "}
          <code className="text-12">https://api.openai.com/v1</code>). Leave empty for the default provider host.
        </>
      ),
      placeholder: "https://openrouter.ai/api/v1",
      error: Boolean(errors.LLM_BASE_URL),
      required: false,
    },
    {
      key: "LLM_MODEL",
      type: "text",
      label: "LLM Model",
      description: (
        <>
          Any model id your endpoint accepts (BYOK). Examples: <code className="text-12">gpt-4o-mini</code>,{" "}
          <code className="text-12">anthropic/claude-3.5-sonnet</code>.
        </>
      ),
      placeholder: "gpt-4o-mini",
      error: Boolean(errors.LLM_MODEL),
      required: false,
    },
    {
      key: "LLM_API_KEY",
      type: "password",
      label: "API key",
      description: <>Your provider API key (stored encrypted). Required for Plane AI features.</>,
      placeholder: "sk-... or provider-specific key",
      error: Boolean(errors.LLM_API_KEY),
      required: false,
    },
  ];

  const onSubmit = async (formData: AIFormValues) => {
    const payload: Partial<AIFormValues> = { ...formData };

    await updateInstanceConfigurations(payload)
      .then(() =>
        setToast({
          type: TOAST_TYPE.SUCCESS,
          title: "Success",
          message: "AI Settings updated successfully",
        })
      )
      .catch((err) => console.error(err));
  };

  return (
    <div className="space-y-8">
      <div className="space-y-3">
        <div>
          <div className="pb-1 text-18 font-medium text-primary">Plane AI (BYOK)</div>
          <div className="text-13 font-regular text-tertiary">
            Bring your own key and optional custom endpoint. Works with OpenAI and any OpenAI-compatible API.
          </div>
        </div>
        <div className="grid-col grid w-full grid-cols-1 items-center justify-between gap-x-12 gap-y-8 lg:grid-cols-2">
          {aiFormFields.map((field) => (
            <ControllerInput
              key={field.key}
              control={control}
              type={field.type}
              name={field.key}
              label={field.label}
              description={field.description}
              placeholder={field.placeholder}
              error={field.error}
              required={field.required}
            />
          ))}
        </div>
      </div>

      <div className="flex flex-col items-start gap-4">
        <Button variant="primary" size="lg" onClick={handleSubmit(onSubmit)} loading={isSubmitting}>
          {isSubmitting ? "Saving" : "Save changes"}
        </Button>

        <div className="relative inline-flex items-center gap-1.5 rounded-sm border border-accent-subtle bg-accent-subtle px-4 py-2 text-caption-sm-regular text-accent-secondary">
          <Lightbulb className="size-4" />
          <div>
            You can also set <code className="text-12">LLM_API_KEY</code>, <code className="text-12">LLM_MODEL</code>,{" "}
            <code className="text-12">LLM_PROVIDER=custom</code>, and <code className="text-12">LLM_BASE_URL</code> as
            environment variables. Custom models are allowed when provider is custom or{" "}
            <code className="text-12">LLM_ALLOW_CUSTOM_MODEL=1</code>.
          </div>
        </div>
      </div>
    </div>
  );
}
