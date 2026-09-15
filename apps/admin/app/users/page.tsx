"use client";

import Link from "next/link";
import {
  FormEvent,
  useCallback,
  useEffect,
  useState,
} from "react";

import {
  ApiError,
  getAdminUser,
  listAdminUsers,
} from "../../lib/api";
import type {
  AdminUserDetail,
  AdminUserListResponse,
  AdminUserRole,
  AdminUserSummary,
} from "../../lib/types";

const PAGE_SIZE = 50;

function errorMessage(
  error: unknown
): string {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      return (
        "Your admin session is unavailable or expired. "
        + "Sign in again to continue."
      );
    }

    if (error.status === 403) {
      return (
        "This account does not have permission "
        + "to access the admin user directory."
      );
    }

    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "The admin user directory could not be loaded.";
}

function formatDate(
  value: string | null
): string {
  if (!value) {
    return "—";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}

function roleLabel(
  role: AdminUserRole
): string {
  return role === "student"
    ? "Student"
    : "Employer";
}

function displaySecondary(
  user: AdminUserSummary
): string {
  if (user.business_email) {
    return user.business_email;
  }

  if (user.headline) {
    return user.headline;
  }

  return user.user_id;
}

export default function AdminUsersPage() {
  const [queryInput, setQueryInput] =
    useState("");

  const [query, setQuery] =
    useState("");

  const [role, setRole] =
    useState<AdminUserRole | "all">(
      "all"
    );

  const [offset, setOffset] =
    useState(0);

  const [result, setResult] =
    useState<AdminUserListResponse | null>(
      null
    );

  const [selectedUser, setSelectedUser] =
    useState<AdminUserDetail | null>(
      null
    );

  const [loading, setLoading] =
    useState(true);

  const [detailLoading, setDetailLoading] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  const loadUsers = useCallback(
    async () => {
      setLoading(true);
      setError(null);

      try {
        const response = await listAdminUsers({
          query: query || undefined,
          role:
            role === "all"
              ? undefined
              : role,
          offset,
          limit: PAGE_SIZE,
        });

        setResult(response);

        if (
          selectedUser
          && !response.items.some(
            (item) =>
              item.user_id
              === selectedUser.user_id
          )
        ) {
          setSelectedUser(null);
        }
      } catch (loadError) {
        setError(
          errorMessage(loadError)
        );
      } finally {
        setLoading(false);
      }
    },
    [
      offset,
      query,
      role,
      selectedUser,
    ]
  );

  useEffect(() => {
    void loadUsers();
  }, [loadUsers]);

  async function openUser(
    userId: string
  ) {
    setDetailLoading(true);
    setError(null);

    try {
      const detail =
        await getAdminUser(userId);

      setSelectedUser(detail);
    } catch (loadError) {
      setError(
        errorMessage(loadError)
      );
    } finally {
      setDetailLoading(false);
    }
  }

  function submitSearch(
    event: FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();
    setOffset(0);
    setQuery(
      queryInput.trim()
    );
  }

  function resetSearch() {
    setQueryInput("");
    setQuery("");
    setRole("all");
    setOffset(0);
  }

  const total = result?.total ?? 0;
  const items = result?.items ?? [];

  const canPrevious =
    offset > 0;

  const canNext =
    offset + PAGE_SIZE < total;

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
        <header
          style={{
            display: "flex",
            gap: "18px",
            alignItems: "flex-start",
            justifyContent: "space-between",
            flexWrap: "wrap",
            marginBottom: "24px",
          }}
        >
          <div>
            <p
              style={{
                color: "#8da2bd",
                margin: "0 0 6px",
                fontSize: "13px",
              }}
            >
              InternMatch Admin / Trust & Safety
            </p>

            <h1
              style={{
                margin: 0,
                fontSize: "28px",
              }}
            >
              Users
            </h1>

            <p
              style={{
                color: "#aebdd0",
                margin: "8px 0 0",
                maxWidth: "720px",
              }}
            >
              Search InternMatch-owned student
              and employer records, inspect
              account context, and review
              administrative audit history.
              Authentication credentials and
              private document storage metadata
              are never exposed here.
            </p>
          </div>

          <Link
            href="/login"
            style={{
              color: "#d7e7fb",
              border: "1px solid #334155",
              borderRadius: "10px",
              padding: "9px 12px",
              textDecoration: "none",
            }}
          >
            Admin login
          </Link>
        </header>

        <nav
          aria-label="Administration"
          style={{
            display: "flex",
            gap: "8px",
            flexWrap: "wrap",
            marginBottom: "22px",
          }}
        >
          {[
            ["/", "Organization reviews"],
            ["/listings", "Internship listings"],
            ["/compliance", "Compliance reviews"],
            ["/users", "Users"],
          ].map(([href, label]) => (
            <Link
              key={href}
              href={href}
              style={{
                color:
                  href === "/users"
                    ? "#07111f"
                    : "#d7e7fb",
                background:
                  href === "/users"
                    ? "#f8fafc"
                    : "#101c2d",
                border: "1px solid #334155",
                borderRadius: "10px",
                padding: "9px 12px",
                textDecoration: "none",
                fontWeight: 600,
              }}
            >
              {label}
            </Link>
          ))}
        </nav>

        <section
          style={{
            background: "#0c1727",
            border: "1px solid #243449",
            borderRadius: "16px",
            padding: "16px",
            marginBottom: "18px",
          }}
        >
          <form
            onSubmit={submitSearch}
            style={{
              display: "grid",
              gridTemplateColumns:
                "minmax(220px, 1fr) 180px auto auto",
              gap: "10px",
            }}
          >
            <input
              value={queryInput}
              onChange={(event) => {
                setQueryInput(
                  event.target.value
                );
              }}
              placeholder={
                "Search name, headline, business email, "
                + "user ID, organization ID..."
              }
              aria-label="Search users"
              style={{
                minWidth: 0,
                border: "1px solid #334155",
                borderRadius: "10px",
                background: "#07111f",
                color: "#f8fafc",
                padding: "11px 12px",
              }}
            />

            <select
              value={role}
              onChange={(event) => {
                const nextRole = event.target.value;

                setRole(
                  nextRole === "student" || nextRole === "employer"
                    ? nextRole
                    : "all"
                );
                setOffset(0);
              }}
              aria-label="Filter by role"
              style={{
                border: "1px solid #334155",
                borderRadius: "10px",
                background: "#07111f",
                color: "#f8fafc",
                padding: "11px 12px",
              }}
            >
              <option value="all">
                All roles
              </option>

              <option value="student">
                Students
              </option>

              <option value="employer">
                Employers
              </option>
            </select>

            <button
              type="submit"
              style={{
                border: 0,
                borderRadius: "10px",
                background: "#f8fafc",
                color: "#07111f",
                fontWeight: 700,
                padding: "11px 15px",
                cursor: "pointer",
              }}
            >
              Search
            </button>

            <button
              type="button"
              onClick={resetSearch}
              style={{
                border: "1px solid #334155",
                borderRadius: "10px",
                background: "transparent",
                color: "#d7e7fb",
                padding: "11px 15px",
                cursor: "pointer",
              }}
            >
              Reset
            </button>
          </form>
        </section>

        {error ? (
          <div
            role="alert"
            style={{
              border: "1px solid #7f1d1d",
              background: "#2a1117",
              borderRadius: "12px",
              padding: "12px 14px",
              marginBottom: "18px",
              color: "#fecaca",
            }}
          >
            {error}
          </div>
        ) : null}

        <div
          style={{
            display: "grid",
            gridTemplateColumns:
              "minmax(0, 1.1fr) minmax(340px, 0.9fr)",
            gap: "18px",
            alignItems: "start",
          }}
        >
          <section
            style={{
              background: "#0c1727",
              border: "1px solid #243449",
              borderRadius: "16px",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                padding: "15px 16px",
                borderBottom: "1px solid #243449",
                display: "flex",
                justifyContent: "space-between",
                gap: "12px",
              }}
            >
              <strong>User directory</strong>

              <span
                style={{
                  color: "#8da2bd",
                }}
              >
                {total} result{total === 1 ? "" : "s"}
              </span>
            </div>

            {loading ? (
              <p
                style={{
                  padding: "18px",
                  color: "#aebdd0",
                }}
              >
                Loading users...
              </p>
            ) : items.length === 0 ? (
              <p
                style={{
                  padding: "18px",
                  color: "#aebdd0",
                }}
              >
                No users match the current filters.
              </p>
            ) : (
              <div>
                {items.map((user) => {
                  const selected =
                    selectedUser?.user_id
                    === user.user_id;

                  return (
                    <button
                      key={user.user_id}
                      type="button"
                      onClick={() => {
                        void openUser(
                          user.user_id
                        );
                      }}
                      style={{
                        width: "100%",
                        textAlign: "left",
                        padding: "15px 16px",
                        border: 0,
                        borderBottom:
                          "1px solid #1d2d42",
                        background: selected
                          ? "#14253a"
                          : "transparent",
                        color: "#f8fafc",
                        cursor: "pointer",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          justifyContent:
                            "space-between",
                          gap: "12px",
                          alignItems: "flex-start",
                        }}
                      >
                        <div
                          style={{
                            minWidth: 0,
                          }}
                        >
                          <strong>
                            {user.display_name}
                          </strong>

                          <div
                            style={{
                              marginTop: "5px",
                              color: "#9fb1c7",
                              overflowWrap:
                                "anywhere",
                            }}
                          >
                            {displaySecondary(user)}
                          </div>
                        </div>

                        <div
                          style={{
                            display: "flex",
                            gap: "5px",
                            flexWrap: "wrap",
                            justifyContent:
                              "flex-end",
                          }}
                        >
                          {user.roles.map(
                            (userRole) => (
                              <span
                                key={userRole}
                                style={{
                                  border:
                                    "1px solid #3b516c",
                                  borderRadius: "999px",
                                  padding: "4px 7px",
                                  fontSize: "12px",
                                  color: "#c7d8ec",
                                }}
                              >
                                {roleLabel(
                                  userRole
                                )}
                              </span>
                            )
                          )}
                        </div>
                      </div>

                      {user.verification_status ? (
                        <div
                          style={{
                            marginTop: "7px",
                            fontSize: "12px",
                            color: "#8da2bd",
                          }}
                        >
                          Organization status:{" "}
                          {user.verification_status}
                        </div>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            )}

            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                gap: "10px",
                padding: "13px 16px",
              }}
            >
              <button
                type="button"
                disabled={!canPrevious}
                onClick={() => {
                  setOffset(
                    Math.max(
                      0,
                      offset - PAGE_SIZE
                    )
                  );
                }}
                style={{
                  border: "1px solid #334155",
                  borderRadius: "8px",
                  background: "transparent",
                  color: canPrevious
                    ? "#f8fafc"
                    : "#64748b",
                  padding: "8px 11px",
                  cursor: canPrevious
                    ? "pointer"
                    : "default",
                }}
              >
                Previous
              </button>

              <span
                style={{
                  color: "#8da2bd",
                  fontSize: "13px",
                  alignSelf: "center",
                }}
              >
                {total === 0
                  ? "0"
                  : `${offset + 1}-${Math.min(
                      offset + PAGE_SIZE,
                      total
                    )}`
                }{" "}
                of {total}
              </span>

              <button
                type="button"
                disabled={!canNext}
                onClick={() => {
                  setOffset(
                    offset + PAGE_SIZE
                  );
                }}
                style={{
                  border: "1px solid #334155",
                  borderRadius: "8px",
                  background: "transparent",
                  color: canNext
                    ? "#f8fafc"
                    : "#64748b",
                  padding: "8px 11px",
                  cursor: canNext
                    ? "pointer"
                    : "default",
                }}
              >
                Next
              </button>
            </div>
          </section>

          <section
            style={{
              background: "#0c1727",
              border: "1px solid #243449",
              borderRadius: "16px",
              padding: "16px",
              minHeight: "320px",
            }}
          >
            {detailLoading ? (
              <p
                style={{
                  color: "#aebdd0",
                }}
              >
                Loading user details...
              </p>
            ) : !selectedUser ? (
              <>
                <strong>User details</strong>

                <p
                  style={{
                    color: "#aebdd0",
                    lineHeight: 1.6,
                  }}
                >
                  Select a user to inspect safe
                  account metadata and the
                  administrative audit timeline.
                </p>
              </>
            ) : (
              <>
                <div
                  style={{
                    marginBottom: "18px",
                  }}
                >
                  <p
                    style={{
                      margin: 0,
                      color: "#8da2bd",
                      fontSize: "12px",
                    }}
                  >
                    User
                  </p>

                  <h2
                    style={{
                      margin: "4px 0 7px",
                      fontSize: "21px",
                    }}
                  >
                    {selectedUser.display_name}
                  </h2>

                  <code
                    style={{
                      color: "#9fb1c7",
                      overflowWrap: "anywhere",
                    }}
                  >
                    {selectedUser.user_id}
                  </code>
                </div>

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns:
                      "repeat(2, minmax(0, 1fr))",
                    gap: "10px",
                    marginBottom: "22px",
                  }}
                >
                  <DetailField
                    label="Roles"
                    value={selectedUser.roles
                      .map(roleLabel)
                      .join(", ")}
                  />

                  <DetailField
                    label="Country"
                    value={
                      selectedUser.country_code
                      ?? "—"
                    }
                  />

                  <DetailField
                    label="Business email"
                    value={
                      selectedUser.business_email
                      ?? "—"
                    }
                  />

                  <DetailField
                    label="Organization status"
                    value={
                      selectedUser
                        .verification_status
                      ?? "—"
                    }
                  />

                  <DetailField
                    label="Organization type"
                    value={
                      selectedUser
                        .organization_type
                      ?? "—"
                    }
                  />

                  <DetailField
                    label="Updated"
                    value={formatDate(
                      selectedUser.updated_at
                    )}
                  />
                </div>

                <div>
                  <div
                    style={{
                      display: "flex",
                      justifyContent:
                        "space-between",
                      gap: "10px",
                      marginBottom: "10px",
                    }}
                  >
                    <strong>
                      Audit timeline
                    </strong>

                    <span
                      style={{
                        color: "#8da2bd",
                        fontSize: "12px",
                      }}
                    >
                      {
                        selectedUser
                          .audit_events.length
                      }{" "}
                      events
                    </span>
                  </div>

                  {selectedUser.audit_events
                    .length === 0 ? (
                    <p
                      style={{
                        color: "#aebdd0",
                        lineHeight: 1.6,
                      }}
                    >
                      No employer verification or
                      compliance audit events are
                      recorded for this account.
                    </p>
                  ) : (
                    <div
                      style={{
                        display: "grid",
                        gap: "9px",
                      }}
                    >
                      {selectedUser.audit_events.map(
                        (event, index) => (
                          <article
                            key={
                              event.source
                              + event.related_id
                              + event.created_at
                              + String(index)
                            }
                            style={{
                              border:
                                "1px solid #243449",
                              borderRadius:
                                "10px",
                              padding:
                                "11px 12px",
                              background:
                                "#091424",
                            }}
                          >
                            <div
                              style={{
                                display: "flex",
                                justifyContent:
                                  "space-between",
                                gap: "10px",
                                flexWrap: "wrap",
                              }}
                            >
                              <strong>
                                {event.action}
                              </strong>

                              <span
                                style={{
                                  color:
                                    "#8da2bd",
                                  fontSize:
                                    "12px",
                                }}
                              >
                                {formatDate(
                                  event.created_at
                                )}
                              </span>
                            </div>

                            <p
                              style={{
                                color: "#9fb1c7",
                                margin:
                                  "7px 0 0",
                                fontSize:
                                  "13px",
                              }}
                            >
                              {event.source
                                .split("_").join(" ")}

                              {event.previous_status
                              || event.new_status
                                ? (
                                  " · "
                                  + (
                                    event.previous_status
                                    ?? "—"
                                  )
                                  + " → "
                                  + (
                                    event.new_status
                                    ?? "—"
                                  )
                                )
                                : ""}
                            </p>

                            {event.reason_code ? (
                              <p
                                style={{
                                  color:
                                    "#aebdd0",
                                  margin:
                                    "7px 0 0",
                                  fontSize:
                                    "13px",
                                }}
                              >
                                Reason:{" "}
                                {
                                  event.reason_code
                                }
                              </p>
                            ) : null}

                            {event.internal_note ? (
                              <p
                                style={{
                                  borderTop:
                                    "1px solid #243449",
                                  paddingTop:
                                    "8px",
                                  margin:
                                    "8px 0 0",
                                  color:
                                    "#cbd5e1",
                                  lineHeight:
                                    1.5,
                                  fontSize:
                                    "13px",
                                }}
                              >
                                Internal note:{" "}
                                {
                                  event.internal_note
                                }
                              </p>
                            ) : null}
                          </article>
                        )
                      )}
                    </div>
                  )}
                </div>
              </>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}

function DetailField({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div
      style={{
        border: "1px solid #243449",
        borderRadius: "9px",
        padding: "9px 10px",
        minWidth: 0,
      }}
    >
      <span
        style={{
          display: "block",
          color: "#8da2bd",
          fontSize: "11px",
          marginBottom: "4px",
        }}
      >
        {label}
      </span>

      <strong
        style={{
          display: "block",
          fontSize: "13px",
          overflowWrap: "anywhere",
        }}
      >
        {value}
      </strong>
    </div>
  );
}
