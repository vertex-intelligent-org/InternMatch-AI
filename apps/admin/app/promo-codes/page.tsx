"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  ApiError,
  createAdminPromoCampaign,
  listAdminPromoCampaigns,
  publishAdminPromoCampaign,
  retireAdminPromoCampaign,
} from "../../lib/api";

import type {
  AdminPromoCampaign,
  PromoAudience,
} from "../../lib/types";


function messageForError(
  error: unknown
): string {
  if (error instanceof ApiError) {
    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Promo campaign operation failed.";
}


function formatDate(
  value: string | null
): string {
  if (!value) {
    return "-";
  }

  const parsed = new Date(value);

  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString();
}


function generatePrivateCode(
  audience: PromoAudience
): string {
  const bytes =
    new Uint8Array(12);

  crypto.getRandomValues(bytes);

  const random =
    Array.from(bytes)
      .map(
        (value) =>
          value
            .toString(16)
            .padStart(2, "0")
            .toUpperCase()
      )
      .join("");

  const prefix =
    audience === "student"
      ? "STU7"
      : "EMP7";

  return prefix + "-" + random;
}


export default function PromoCodesPage() {
  const [campaigns, setCampaigns] =
    useState<AdminPromoCampaign[]>([]);

  const [studentCode, setStudentCode] =
    useState("");

  const [employerCode, setEmployerCode] =
    useState("");

  const [studentPublish, setStudentPublish] =
    useState(true);

  const [employerPublish, setEmployerPublish] =
    useState(true);

  const [showStudent, setShowStudent] =
    useState(false);

  const [showEmployer, setShowEmployer] =
    useState(false);

  const [loading, setLoading] =
    useState(true);

  const [working, setWorking] =
    useState<string | null>(null);

  const [error, setError] =
    useState<string | null>(null);


  const loadCampaigns =
    useCallback(async () => {
      setLoading(true);
      setError(null);

      try {
        const result =
          await listAdminPromoCampaigns();

        setCampaigns(result);
      } catch (loadError) {
        setError(
          messageForError(loadError)
        );
      } finally {
        setLoading(false);
      }
    }, []);


  useEffect(() => {
    void loadCampaigns();
  }, [loadCampaigns]);


  const campaignsByAudience =
    useMemo(
      () => ({
        student:
          campaigns.filter(
            (item) =>
              item.audience
              === "student"
          ),
        employer:
          campaigns.filter(
            (item) =>
              item.audience
              === "employer"
          ),
      }),
      [campaigns]
    );


  async function createCampaign(
    audience: PromoAudience
  ) {
    const rawCode =
      audience === "student"
        ? studentCode
        : employerCode;

    const code =
      rawCode.trim().toUpperCase();

    if (
      code.length < 16
      || code.length > 64
    ) {
      setError(
        "Promo codes must contain 16 to 64 characters."
      );
      return;
    }

    const publish =
      audience === "student"
        ? studentPublish
        : employerPublish;

    setWorking(
      "create:" + audience
    );
    setError(null);

    try {
      await createAdminPromoCampaign({
        audience,
        code,
        publish,
      });

      // The backend intentionally never returns
      // the raw code. Clear local state after save.
      if (audience === "student") {
        setStudentCode("");
        setShowStudent(false);
      } else {
        setEmployerCode("");
        setShowEmployer(false);
      }

      await loadCampaigns();
    } catch (createError) {
      setError(
        messageForError(createError)
      );
    } finally {
      setWorking(null);
    }
  }


  async function publishCampaign(
    campaignId: string
  ) {
    setWorking(
      "publish:" + campaignId
    );
    setError(null);

    try {
      await publishAdminPromoCampaign(
        campaignId
      );

      await loadCampaigns();
    } catch (publishError) {
      setError(
        messageForError(publishError)
      );
    } finally {
      setWorking(null);
    }
  }


  async function retireCampaign(
    campaignId: string
  ) {
    const confirmed =
      window.confirm(
        "Retire this promo code? "
        + "New redemptions will stop. "
        + "Users who already redeemed it "
        + "keep their remaining Pro access."
      );

    if (!confirmed) {
      return;
    }

    setWorking(
      "retire:" + campaignId
    );
    setError(null);

    try {
      await retireAdminPromoCampaign(
        campaignId
      );

      await loadCampaigns();
    } catch (retireError) {
      setError(
        messageForError(retireError)
      );
    } finally {
      setWorking(null);
    }
  }


  async function copyCode(
    value: string
  ) {
    if (!value) {
      return;
    }

    try {
      await navigator.clipboard.writeText(
        value
      );
    } catch {
      setError(
        "The browser could not copy the code."
      );
    }
  }


  function renderAudience(
    audience: PromoAudience
  ) {
    const isStudent =
      audience === "student";

    const code =
      isStudent
        ? studentCode
        : employerCode;

    const publish =
      isStudent
        ? studentPublish
        : employerPublish;

    const showCode =
      isStudent
        ? showStudent
        : showEmployer;

    const title =
      isStudent
        ? "Student Promo"
        : "Employer Promo";

    const subtitle =
      isStudent
        ? "Pro Student for exactly 7 days."
        : "Employer Pro for exactly 7 days.";

    const items =
      campaignsByAudience[audience];

    return (
      <section
        key={audience}
        style={{
          background: "#0c1727",
          border: "1px solid #243449",
          borderRadius: "16px",
          padding: "18px",
        }}
      >
        <h2 style={{ margin: 0 }}>
          {title}
        </h2>

        <p style={{ color: "#9fb0c6" }}>
          {subtitle}
        </p>

        <p
          style={{
            color: "#8da2bd",
            fontSize: "13px",
            lineHeight: 1.5,
          }}
        >
          Each account can successfully redeem
          its role-specific promo only once.
          Rotating or retiring a code never
          removes access already granted.
        </p>

        <div
          style={{
            background: "#07111f",
            border: "1px solid #243449",
            borderRadius: "12px",
            padding: "14px",
          }}
        >
          <strong>
            Create or rotate code
          </strong>

          <p
            style={{
              color: "#8da2bd",
              fontSize: "12px",
            }}
          >
            Copy the raw code before saving.
            The backend stores only a secure
            digest and masked hint.
          </p>

          <input
            type={
              showCode
                ? "text"
                : "password"
            }
            value={code}
            onChange={(event) => {
              const next =
                event.target.value
                  .toUpperCase();

              if (isStudent) {
                setStudentCode(next);
              } else {
                setEmployerCode(next);
              }
            }}
            autoComplete="off"
            spellCheck={false}
            maxLength={64}
            placeholder={
              isStudent
                ? "Private student promo"
                : "Private employer promo"
            }
            style={{
              width: "100%",
              boxSizing: "border-box",
              border: "1px solid #334155",
              borderRadius: "10px",
              background: "#0c1727",
              color: "#f8fafc",
              padding: "11px 12px",
            }}
          />

          <div
            style={{
              display: "flex",
              gap: "8px",
              flexWrap: "wrap",
              marginTop: "9px",
            }}
          >
            <button
              type="button"
              onClick={() => {
                if (isStudent) {
                  setShowStudent(
                    (current) => !current
                  );
                } else {
                  setShowEmployer(
                    (current) => !current
                  );
                }
              }}
            >
              {showCode ? "Hide" : "Show"}
            </button>

            <button
              type="button"
              onClick={() => {
                const generated =
                  generatePrivateCode(
                    audience
                  );

                if (isStudent) {
                  setStudentCode(generated);
                } else {
                  setEmployerCode(generated);
                }
              }}
            >
              Generate
            </button>

            <button
              type="button"
              disabled={!code}
              onClick={() => {
                void copyCode(code);
              }}
            >
              Copy
            </button>
          </div>

          <label
            style={{
              display: "flex",
              gap: "8px",
              alignItems: "center",
              marginTop: "12px",
              fontSize: "13px",
            }}
          >
            <input
              type="checkbox"
              checked={publish}
              onChange={(event) => {
                if (isStudent) {
                  setStudentPublish(
                    event.target.checked
                  );
                } else {
                  setEmployerPublish(
                    event.target.checked
                  );
                }
              }}
            />

            Publish immediately
          </label>

          <button
            type="button"
            disabled={
              !code.trim()
              || working
                === "create:" + audience
            }
            onClick={() => {
              void createCampaign(
                audience
              );
            }}
            style={{
              marginTop: "12px",
            }}
          >
            {working
              === "create:" + audience
              ? "Saving..."
              : publish
                ? "Create and publish"
                : "Save draft"}
          </button>
        </div>

        <div
          style={{
            display: "grid",
            gap: "10px",
            marginTop: "16px",
          }}
        >
          {items.map(
            (campaign) => (
              <article
                key={campaign.id}
                style={{
                  background: "#07111f",
                  border:
                    "1px solid #243449",
                  borderRadius: "12px",
                  padding: "12px",
                }}
              >
                <div>
                  <strong>
                    {campaign.code_hint}
                  </strong>
                </div>

                <p
                  style={{
                    color: "#aebdd0",
                    fontSize: "13px",
                  }}
                >
                  Status: {campaign.status}
                  {" | "}
                  Redemptions: {
                    campaign
                      .redemption_count
                  }
                </p>

                <p
                  style={{
                    color: "#8da2bd",
                    fontSize: "12px",
                  }}
                >
                  Created: {
                    formatDate(
                      campaign.created_at
                    )
                  }
                </p>

                {campaign.status
                  === "draft" ? (
                  <button
                    type="button"
                    disabled={
                      working
                      === (
                        "publish:"
                        + campaign.id
                      )
                    }
                    onClick={() => {
                      void publishCampaign(
                        campaign.id
                      );
                    }}
                  >
                    Publish
                  </button>
                ) : null}

                {campaign.status
                  !== "retired" ? (
                  <button
                    type="button"
                    disabled={
                      working
                      === (
                        "retire:"
                        + campaign.id
                      )
                    }
                    onClick={() => {
                      void retireCampaign(
                        campaign.id
                      );
                    }}
                    style={{
                      marginLeft: "8px",
                    }}
                  >
                    Retire
                  </button>
                ) : null}
              </article>
            )
          )}

          {items.length === 0 ? (
            <p style={{ color: "#8da2bd" }}>
              No campaigns yet.
            </p>
          ) : null}
        </div>
      </section>
    );
  }


  return (
    <main
      style={{
        minHeight: "100vh",
        background: "#07111f",
        color: "#e5edf8",
        padding: "24px",
      }}
    >
      <div
        style={{
          maxWidth: "1500px",
          margin: "0 auto",
        }}
      >
        <header>
          <p style={{ color: "#8da2bd" }}>
            InternMatch Admin / Promotional Access
          </p>

          <h1>
            Promo Codes
          </h1>

          <p
            style={{
              color: "#aebdd0",
              maxWidth: "760px",
              lineHeight: 1.5,
            }}
          >
            Manage separate private student and
            employer promo campaigns. Raw promo
            codes are never returned by the API.
          </p>
        </header>

        <nav
          aria-label="Administration"
          style={{
            display: "flex",
            gap: "8px",
            flexWrap: "wrap",
            margin: "20px 0",
          }}
        >
          {[
            ["/", "Organization reviews"],
            ["/listings", "Internship listings"],
            ["/compliance", "Compliance reviews"],
            ["/users", "Users"],
            ["/promo-codes", "Promo codes"],
          ].map(([href, label]) => (
            <Link
              key={href}
              href={href}
            >
              {label}
            </Link>
          ))}
        </nav>

        {error ? (
          <div
            role="alert"
            style={{
              color: "#fecaca",
              marginBottom: "16px",
            }}
          >
            {error}
          </div>
        ) : null}

        {loading ? (
          <p>
            Loading promo campaigns...
          </p>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                "repeat(auto-fit, minmax(420px, 1fr))",
              gap: "18px",
            }}
          >
            {renderAudience("student")}
            {renderAudience("employer")}
          </div>
        )}
      </div>
    </main>
  );
}
